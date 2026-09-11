"""Verificador da explicação do treinador.

Cada linha citada é reproduzida no tabuleiro a partir da posição declarada,
o primeiro lance é conferido com as três melhores da engine, a avaliação do
fim da linha é comparada com a da engine e cada citação de estudo tem de
existir entre os trechos recuperados. Puro: recebe a função de análise e não
toca em banco nem rede, o que permite reusá-lo na avaliação offline."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable

import chess

from chess_trainer.core.evals import MATE_SCORE, is_mate, mate_in

# (fen, multipv) -> dict no formato de `InteractiveAnalyzer.analyse`
Analisar = Callable[[str, int], dict]

# a mesma expressão do `moveText.ts` do frontend, sem o número do lance
SAN_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8](?:=[QRBN])?)[+#]?(?![A-Za-z0-9-])"
)
CITACAO_RE = re.compile(r"\[c:([^\]\s]+)\]")
MENCAO_ESTUDO_RE = re.compile(r"\b(?:no|na|nos|nas|do|da|dos|das)\s+(?:estudo|cap[ií]tulo|livro)s?\b", re.IGNORECASE)
TOLERANCIA_CP = 100
MIN_PALAVRAS, MAX_PALAVRAS = 60, 400


@dataclass(frozen=True)
class Issue:
    tipo: str
    gravidade: str  # "erro" | "aviso"
    detalhe: str
    linha_idx: int | None = None


@dataclass
class Verificacao:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.gravidade == "erro" for i in self.issues)

    @property
    def erros(self) -> int:
        return sum(1 for i in self.issues if i.gravidade == "erro")

    @property
    def avisos(self) -> int:
        return sum(1 for i in self.issues if i.gravidade == "aviso")

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issues": [asdict(i) for i in self.issues]}


def limpar_san(san: str) -> str:
    """Tira apreciação e xeque/mate: `Qxf7#!` -> `Qxf7`."""
    return san.strip().replace("!", "").replace("?", "").rstrip("+#")


def _fmt(score: int) -> str:
    n = mate_in(score)
    if n is not None:
        return f"mate em {n}" if score > 0 else f"mate em {n} contra"
    return f"{score / 100:+.2f}"


def _score_brancas(board: chess.Board, analise: dict) -> int | None:
    """Avaliação do ponto de vista das brancas; o analisador dá a do lado a mover."""
    if board.is_checkmate():
        stm = -MATE_SCORE
    elif board.is_game_over():
        stm = 0
    else:
        lines = analise.get("lines") or []
        if not lines:
            return None
        stm = int(lines[0]["score"])
    return stm if board.turn == chess.WHITE else -stm


def _num(valor: object) -> int | None:
    """Converte `avaliacao_cp`/`mate_em` para int; aceita float (truncado) e string
    numérica, rejeita bool e qualquer outra coisa não numérica."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    if isinstance(valor, str):
        try:
            return int(float(valor))
        except ValueError:
            return None
    return None


def _analisar_seguro(analisar: Analisar, fen: str, multipv: int, idx: int, v: Verificacao, contexto: str) -> dict | None:
    """Chama o analisador guardando contra a engine fora do ar: registra `engine_indisponivel`
    e devolve None em vez de deixar a exceção escapar."""
    try:
        return analisar(fen, multipv)
    except Exception as exc:  # noqa: BLE001 - engine fora do ar vira issue, não exceção
        v.issues.append(Issue("engine_indisponivel", "erro", f"sem engine para conferir {contexto}: {exc}", idx))
        return None


def verificar(resposta: dict, *, fen_inicial: str, fen_erro: str | None, lances_permitidos: set[str],
              trechos_ids: set[str], analisar: Analisar) -> Verificacao:
    v = Verificacao()
    texto = str(resposta.get("texto") or "")
    linhas = resposta.get("linhas") or []
    lances_em_linhas: set[str] = set()

    for idx, linha in enumerate(linhas):
        inicio = linha.get("inicio", "inicial")
        fen = fen_erro if inicio == "erro" and fen_erro else fen_inicial
        lances = [str(l) for l in (linha.get("lances") or [])]
        lances_em_linhas.update(limpar_san(l) for l in lances)
        board = chess.Board(fen)

        # 1. legalidade: reproduz a linha inteira
        jogados: list[chess.Move] = []
        ilegal: str | None = None
        for san in lances:
            try:
                mv = board.parse_san(limpar_san(san))
            except ValueError:
                ilegal = san
                break
            jogados.append(mv)
            board.push(mv)
        if ilegal is not None:
            v.issues.append(Issue("lance_ilegal", "erro", f"'{ilegal}' não é legal na posição declarada", idx))
            continue
        if not jogados:
            continue

        # 2. aderência: o primeiro lance está entre as três melhores, ou é um lance do exercício
        analise = _analisar_seguro(analisar, fen, 3, idx, v, "a linha")
        if analise is None:
            continue
        principais = [str(l.get("san", "")) for l in analise.get("lines") or []]
        if not any(limpar_san(lances[0]) == limpar_san(s) for s in principais) and jogados[0].uci() not in lances_permitidos:
            v.issues.append(Issue("lance_fora_das_principais", "aviso",
                                  f"'{lances[0]}' não está entre as três melhores da engine nem é um lance do exercício", idx))

        # 3. avaliação no fim da linha
        aval_bruto = linha.get("avaliacao_cp")
        mate_bruto = linha.get("mate_em")
        if aval_bruto is None and mate_bruto is None:
            continue
        aval = mate = None
        invalida = False
        if mate_bruto is not None:
            mate = _num(mate_bruto)
            if mate is None:
                v.issues.append(Issue("avaliacao_invalida", "erro", f"avaliação '{mate_bruto}' não é numérica", idx))
                invalida = True
        if aval_bruto is not None:
            aval = _num(aval_bruto)
            if aval is None:
                v.issues.append(Issue("avaliacao_invalida", "erro", f"avaliação '{aval_bruto}' não é numérica", idx))
                invalida = True
        if invalida:
            continue
        final = _analisar_seguro(analisar, board.fen(), 1, idx, v, "a avaliação")
        if final is None:
            continue
        score = _score_brancas(board, final)
        if score is None:
            v.issues.append(Issue("engine_indisponivel", "erro", "a engine não devolveu avaliação para o fim da linha", idx))
        elif mate is not None:
            n = mate_in(score)
            if n is None or n != mate:
                v.issues.append(Issue("avaliacao_errada", "erro", f"a explicação diz mate em {mate}; a engine dá {_fmt(score)}", idx))
        elif is_mate(score):
            v.issues.append(Issue("avaliacao_errada", "aviso", f"a engine dá {_fmt(score)} onde a explicação dá {aval / 100:+.2f}", idx))
        elif abs(score - aval) > TOLERANCIA_CP:
            v.issues.append(Issue("avaliacao_errada", "erro", f"a explicação dá {aval / 100:+.2f}; a engine dá {score / 100:+.2f}", idx))

    # 4. lances soltos no texto
    for m in SAN_RE.finditer(texto):
        if limpar_san(m.group(0)) not in lances_em_linhas:
            v.issues.append(Issue("lance_sem_linha", "aviso", f"'{m.group(0)}' aparece no texto sem estar em nenhuma linha"))

    # 5. citações
    citadas = set(CITACAO_RE.findall(texto)) | {str(c) for c in (resposta.get("citacoes") or [])}
    for cid in sorted(citadas):
        if cid not in trechos_ids:
            v.issues.append(Issue("citacao_inexistente", "erro", f"a citação '{cid}' não está entre os trechos recuperados"))
    if not citadas and MENCAO_ESTUDO_RE.search(texto):
        v.issues.append(Issue("citacao_ausente", "aviso", "o texto menciona um estudo sem citar o trecho"))

    # 6. tamanho
    n = len(texto.split())
    if n < MIN_PALAVRAS or n > MAX_PALAVRAS:
        v.issues.append(Issue("tamanho", "aviso", f"{n} palavras (esperado entre {MIN_PALAVRAS} e {MAX_PALAVRAS})"))
    return v
