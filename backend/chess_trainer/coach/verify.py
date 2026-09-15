"""Verificador da explicação do treinador.

Cada linha citada é reproduzida no tabuleiro a partir da posição declarada,
o primeiro lance é conferido com as três melhores da engine, a avaliação do
fim da linha é comparada com a da engine, cada citação de estudo tem de
existir entre os trechos recuperados, cada lance numerado da prosa tem de estar
em alguma linha declarada na mesma altura (número e lado) e cada "peça de casa" da prosa (e cada
"apoiada/defendida/atacada por" ela) tem de bater com alguma posição
alcançada. A checagem das demais afirmações da prosa (quem ataca o quê, mais
atacantes do que defensores, cravada, indefesa...) mora em `afirmacoes.py`, que
importa daqui as posições alcançáveis e os auxiliares. Puro: recebe a função de
análise e não toca em banco nem rede, o que permite reusá-lo na avaliação offline."""
from __future__ import annotations

import math
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
# o mesmo lance com o número da anotação na frente: `18.Rac1?`, `32...Qh3`, `8 a5` (grupo 1 = o
# número, grupo 2 = os pontos — duas reticências ou mais querem dizer lance das pretas)
LANCE_NUMERADO_RE = re.compile(
    r"(?<![A-Za-z0-9-])(\d{1,3})[ \t]*(\.{1,4})?[ \t]*"
    r"((?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8](?:=[QRBN])?)[+#]?)(?![A-Za-z0-9-])"
)
CASA_RE = re.compile(r"^[a-h][1-8]$")
CITACAO_RE = re.compile(r"\[c:([^\]\s]+)\]")
MENCAO_ESTUDO_RE = re.compile(r"\b(?:no|na|nos|nas|do|da|dos|das)\s+(?:estudo|cap[ií]tulo|livro)s?\b", re.IGNORECASE)
# "o bispo de f4", "a torre em d8": peça nomeada numa casa
PECA_NA_CASA_RE = re.compile(r"\b(dama|torre|bispo|cavalo|pe[ãa]o|rei)\s+(?:de|do|da|em|no|na)\s+([a-h][1-8])\b", re.IGNORECASE)
# "apoiada pelo cavalo de f5", "defendida pela dama de d4": uma peça sustentando uma casa
RELACAO_RE = re.compile(
    r"\b(apoiad[oa]s?|defendid[oa]s?|protegid[oa]s?|cobert[oa]s?|atacad[oa]s?|controlad[oa]s?)\s+pel[oa]s?\s+"
    r"(dama|torre|bispo|cavalo|pe[ãa]o|rei)\s+(?:de|do|da|em|no|na)\s+([a-h][1-8])\b", re.IGNORECASE)
# fim de frase: pontuação seguida de espaço ou do fim do texto (o ponto de `2.Qxg7#` não conta)
FRASE_RE = re.compile(r"[.!?:;](?:\s+|$)")
TIPO_DA_PECA = {"dama": chess.QUEEN, "torre": chess.ROOK, "bispo": chess.BISHOP, "cavalo": chess.KNIGHT,
                "peão": chess.PAWN, "peao": chess.PAWN, "rei": chess.KING}
# os dois `inicio` que partem do lance nulo: a ameaça do adversário na posição do
# exercício e na posição do erro
INICIOS_DE_AMEACA = ("ameaca", "ameaca_erro")
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
    """Converte `avaliacao_cp`/`mate_em` para int; aceita float finito (truncado) e
    string numérica finita, rejeita bool, infinito/NaN e qualquer outra coisa não
    numérica -- nunca levanta exceção, sempre devolve None quando não dá."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    try:
        f = valor if isinstance(valor, float) else float(valor)  # type: ignore[arg-type]
        if not math.isfinite(f):
            return None
        return int(f)
    except (ValueError, OverflowError, TypeError):
        return None


def _analisar_seguro(analisar: Analisar, fen: str, multipv: int, idx: int, v: Verificacao, contexto: str) -> dict | None:
    """Chama o analisador guardando contra a engine fora do ar: registra `engine_indisponivel`
    e devolve None em vez de deixar a exceção escapar."""
    try:
        return analisar(fen, multipv)
    except Exception as exc:  # noqa: BLE001 - engine fora do ar vira issue, não exceção
        v.issues.append(Issue("engine_indisponivel", "erro", f"sem engine para conferir {contexto}: {exc}", idx))
        return None


def _tabuleiro(fen: str | None) -> chess.Board | None:
    try:
        return chess.Board(fen) if fen else None
    except ValueError:
        return None


def _base_da_linha(inicio: str, fen_inicial: str, fen_erro: str | None) -> tuple[chess.Board | None, str]:
    """A posição de onde a linha parte: a do exercício, a do erro, ou — nas linhas de
    ameaça — a do lance nulo, em que o adversário move como se o aluno passasse a vez.
    Devolve (tabuleiro, motivo): o tabuleiro é None quando não dá para partir dali, e o
    motivo é o detalhe que a linha recebe como `lance_ilegal`."""
    if inicio == "ameaca_erro" and not fen_erro:
        return None, "linha de ameaça: este exercício não tem posição do erro"
    fen = fen_erro if inicio in ("erro", "ameaca_erro") and fen_erro else fen_inicial
    board = _tabuleiro(fen)
    if board is None:
        return None, f"a FEN da posição declarada não presta: '{fen}'"
    if inicio not in INICIOS_DE_AMEACA:
        return board, ""
    if board.is_check():
        return None, "linha de ameaça: o lado a mover está em xeque, não dá para passar a vez"
    board.push(chess.Move.null())
    return board, ""


def fen_de_onde_a_linha_parte(inicio: str, fen_inicial: str, fen_erro: str | None) -> str | None:
    """A FEN da base da linha — já com o lance nulo das linhas de ameaça —, ou `None` quando
    não dá para partir dali (exercício sem posição do erro, lado a mover em xeque). É o que a
    API manda no `fen_inicio` de cada linha, para o cartão resolver os lances numerados da
    prosa pela linha certa em vez de os ancorar todos na posição do exercício."""
    board, _ = _base_da_linha(inicio, fen_inicial, fen_erro)
    return board.fen() if board is not None else None


def _posicoes_alcancaveis(fen_inicial: str, fen_erro: str | None, linhas: list) -> list[chess.Board]:
    """Toda posição que a explicação alcança: as duas do exercício, as dos lances nulos (de
    onde saem as ameaças do adversário nas duas) e cada posição depois de um prefixo legal de
    cada linha. É nelas que os mates e os xeques escritos no texto têm de ser verdade — antes o
    verificador conferia as linhas e deixava passar a prosa."""
    boards: list[chess.Board] = []
    vistas: set[str] = set()

    def guardar(board: chess.Board) -> None:
        if board.fen() not in vistas:
            vistas.add(board.fen())
            boards.append(board)

    for fen in (fen_inicial, fen_erro):
        board = _tabuleiro(fen)
        if board is not None:
            guardar(board)
    for inicio in INICIOS_DE_AMEACA:
        passa, _ = _base_da_linha(inicio, fen_inicial, fen_erro)
        if passa is not None:
            guardar(passa)
    for linha in linhas:
        inicio = linha.get("inicio", "inicial")
        board, _ = _base_da_linha(inicio, fen_inicial, fen_erro)
        if board is None:
            continue
        for san in (str(l) for l in (linha.get("lances") or [])):
            try:
                board.push(board.parse_san(limpar_san(san)))
            except ValueError:
                break
            guardar(board.copy())
    return boards


def _alturas_das_linhas(fen_inicial: str, fen_erro: str | None, linhas: list) -> set[tuple[int, bool, str]]:
    """Cada lance de cada linha declarada pela altura em que ele é jogado: (número do lance, é das
    pretas, SAN limpo). É contra este conjunto que os lances numerados da prosa são conferidos — o
    lance nulo das linhas de ameaça já entra na conta do número, porque `_base_da_linha` o empurra."""
    alturas: set[tuple[int, bool, str]] = set()
    for linha in linhas:
        board, _ = _base_da_linha(str(linha.get("inicio") or "inicial"), fen_inicial, fen_erro)
        if board is None:
            continue
        for san in (str(l) for l in (linha.get("lances") or [])):
            try:
                mv = board.parse_san(limpar_san(san))
            except ValueError:
                break
            alturas.add((board.fullmove_number, board.turn == chess.BLACK, limpar_san(board.san(mv))))
            board.push(mv)
    return alturas


def posicoes_da_resposta(resposta: dict, *, fen_inicial: str, fen_erro: str | None) -> list[chess.Board]:
    """As posições alcançáveis de uma resposta estruturada: a mesma lista que `verificar` usa
    nas regras 4 e 7, para a checagem de afirmações conferir contra as mesmas posições."""
    return _posicoes_alcancaveis(fen_inicial, fen_erro, resposta.get("linhas") or [])


def _da_xeque(boards: list[chess.Board], san: str, *, mate: bool) -> bool:
    """O lance é legal e dá xeque (ou mate, quando `mate`) em pelo menos uma das posições."""
    for board in boards:
        try:
            mv = board.parse_san(san)
        except ValueError:
            continue
        if not board.gives_check(mv):
            continue
        if not mate:
            return True
        board.push(mv)
        eh_mate = board.is_checkmate()
        board.pop()
        if eh_mate:
            return True
    return False


def _casa_na_prosa(token: str, fen_inicial: str, fen_erro: str | None) -> bool:
    """`h1`, `g3`: nome de casa no meio da frase. Só conta como lance solto quando é um
    lance de peão legal numa das posições do exercício."""
    if not CASA_RE.match(token):
        return False
    for fen in (fen_inicial, fen_erro):
        board = _tabuleiro(fen)
        if board is None:
            continue
        try:
            board.parse_san(token)
        except ValueError:
            continue
        return False
    return True


def _peca_existe(boards: list[chess.Board], tipo: int, casa: int) -> bool:
    """Uma peça desse tipo (de qualquer cor) está na casa em pelo menos uma das posições."""
    return any(board.piece_type_at(casa) == tipo for board in boards)


def _peca_ataca(boards: list[chess.Board], tipo: int, casa: int, alvo: int) -> bool:
    """Em pelo menos uma das posições a peça está na casa E a casa alvo está no alcance dela
    (`attacks` é geometria: ignora de quem é a peça no alvo e dá as casas de captura do peão,
    que é exatamente o que "apoia", "defende" e "ataca" querem dizer)."""
    return any(board.piece_type_at(casa) == tipo and alvo in board.attacks(casa) for board in boards)


def _destino_do_san(token: str) -> str | None:
    """`Qxg7#` -> `g7`, `e8=Q+` -> `e8`; roque não tem casa de chegada única."""
    limpo = limpar_san(token)
    if limpo.startswith("O-O"):
        return None
    limpo = limpo.split("=")[0]
    return limpo[-2:] if CASA_RE.match(limpo[-2:]) else None


def _alvo_da_relacao(prefixo: str) -> str | None:
    """A casa de que a frase fala antes de "apoiada pelo …": a de chegada do último lance
    escrito, ou a da última "peça de casa" (o sujeito: "a dama de d4 está atacada pelo …"),
    o que vier por último. Sem nenhum dos dois, não há o que conferir."""
    candidatos: list[tuple[int, str]] = []
    for m in SAN_RE.finditer(prefixo):
        destino = _destino_do_san(m.group(0))
        if destino is not None:
            candidatos.append((m.end(), destino))
    for m in PECA_NA_CASA_RE.finditer(prefixo):
        candidatos.append((m.end(), m.group(2).lower()))
    return max(candidatos)[1] if candidatos else None


def _pecas_e_relacoes(texto: str, alcancaveis: list[chess.Board]) -> list[Issue]:
    """Regra 7: toda "peça de casa" escrita existe em alguma posição alcançável, e toda
    "apoiada/defendida/atacada pela peça de casa" é geometria de verdade nessa posição — o
    caso real era um mate certo "apoiado pelo bispo de f4" em que quem apoiava era o cavalo."""
    achados: dict[str, Issue] = {}

    def registrar(detalhe: str) -> None:
        achados.setdefault(detalhe, Issue("peca_falsa", "erro", detalhe))

    for m in PECA_NA_CASA_RE.finditer(texto):
        nome, casa = m.group(1).lower(), m.group(2).lower()
        if not _peca_existe(alcancaveis, TIPO_DA_PECA[nome], chess.parse_square(casa)):
            registrar(f"não há {nome} em {casa} em nenhuma posição da explicação")
    for frase in FRASE_RE.split(texto):
        for m in RELACAO_RE.finditer(frase):
            nome, casa = m.group(2).lower(), m.group(3).lower()
            alvo = _alvo_da_relacao(frase[:m.start()])
            if alvo is None:
                continue
            if not _peca_ataca(alcancaveis, TIPO_DA_PECA[nome], chess.parse_square(casa), chess.parse_square(alvo)):
                registrar(f"o {nome} de {casa} não ataca {alvo} em nenhuma posição da explicação")
    return list(achados.values())


def verificar(resposta: dict, *, fen_inicial: str, fen_erro: str | None, lances_permitidos: set[str],
              trechos_ids: set[str], analisar: Analisar) -> Verificacao:
    v = Verificacao()
    texto = str(resposta.get("texto") or "")
    linhas = resposta.get("linhas") or []
    lances_em_linhas: set[str] = set()

    for idx, linha in enumerate(linhas):
        inicio = linha.get("inicio", "inicial")
        lances = [str(l) for l in (linha.get("lances") or [])]
        lances_em_linhas.update(limpar_san(l) for l in lances)
        # a linha de ameaça parte do lance nulo: sem posição do erro ou em xeque, não dá
        board, motivo = _base_da_linha(inicio, fen_inicial, fen_erro)
        if board is None:
            v.issues.append(Issue("lance_ilegal", "erro", motivo, idx))
            continue
        fen = board.fen()

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
        # numa linha de ameaça o primeiro lance é do adversário: os lances do exercício não valem
        permitido = inicio not in INICIOS_DE_AMEACA and jogados[0].uci() in lances_permitidos
        if not any(limpar_san(lances[0]) == limpar_san(s) for s in principais) and not permitido:
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
            # `mate_em` é assinado (positivo = as brancas dão mate, negativo = as pretas);
            # `0` quer dizer "a linha termina em mate" e vale para qualquer um dos dois lados
            sinal_certo = mate == 0 or (mate > 0) == (score > 0)
            if n is None or n != abs(mate) or not sinal_certo:
                v.issues.append(Issue("avaliacao_errada", "erro", f"a explicação diz mate em {mate}; a engine dá {_fmt(score)}", idx))
        elif is_mate(score):
            v.issues.append(Issue("avaliacao_errada", "aviso", f"a engine dá {_fmt(score)} onde a explicação dá {aval / 100:+.2f}", idx))
        elif abs(score - aval) > TOLERANCIA_CP:
            v.issues.append(Issue("avaliacao_errada", "erro", f"a explicação dá {aval / 100:+.2f}; a engine dá {score / 100:+.2f}", idx))

    # 4. lances soltos, mates e xeques no texto
    alcancaveis = posicoes_da_resposta(resposta, fen_inicial=fen_inicial, fen_erro=fen_erro)
    # o mesmo lance repetido na prosa não rende dois avisos iguais: dedupe por (tipo, detalhe)
    do_texto: dict[tuple[str, str], Issue] = {}
    for m in SAN_RE.finditer(texto):
        token = m.group(0)
        limpo = limpar_san(token)
        if token.endswith("#") and not _da_xeque(alcancaveis, limpo, mate=True):
            issue = Issue("mate_falso", "erro", f"'{token}' não é mate em nenhuma posição da explicação")
            do_texto.setdefault((issue.tipo, issue.detalhe), issue)
        elif token.endswith("+") and not _da_xeque(alcancaveis, limpo, mate=False):
            issue = Issue("xeque_falso", "aviso", f"'{token}' não dá xeque em nenhuma posição da explicação")
            do_texto.setdefault((issue.tipo, issue.detalhe), issue)
        if limpo not in lances_em_linhas and not _casa_na_prosa(token, fen_inicial, fen_erro):
            issue = Issue("lance_sem_linha", "aviso", f"'{token}' aparece no texto sem estar em nenhuma linha")
            do_texto.setdefault((issue.tipo, issue.detalhe), issue)
    # 4b. lance numerado da prosa que nenhuma linha declara naquela altura: o cartão não tem como
    # achar a posição dele e acaba jogando o lance a partir do exercício, num tabuleiro que não é o
    # da explicação. A prosa pode pular lances; a linha, não
    alturas = _alturas_das_linhas(fen_inicial, fen_erro, linhas)
    for m in LANCE_NUMERADO_RE.finditer(texto):
        san = limpar_san(m.group(3))
        # o lance que nenhuma linha traz já virou `lance_sem_linha` na regra 4: repetir a falta
        # aqui só renderia dois avisos para o mesmo lance. O que 4b pega é o lance declarado que
        # a prosa numera noutra altura
        if san not in lances_em_linhas:
            continue
        altura = (int(m.group(1)), len(m.group(2) or "") >= 2, san)
        if altura not in alturas:
            issue = Issue("lance_fora_de_linha", "aviso",
                          f"'{m.group(0)}' não aparece nessa altura em nenhuma linha declarada")
            do_texto.setdefault((issue.tipo, issue.detalhe), issue)
    v.issues.extend(do_texto.values())

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

    # 7. peças e relações: "o bispo de f4" existe, e "apoiada pelo bispo de f4" é geometria
    v.issues.extend(_pecas_e_relacoes(texto, alcancaveis))
    return v
