"""Checagem de afirmações da explicação (spec §5, regra 8).

Regex por formato de frase não dá conta da prosa ("o cavalo de f5 e a dama de g4
atacam d4 mais vezes do que as pretas defendem"). Aqui um segundo modelo, barato,
lê a explicação e devolve cada afirmação sobre o tabuleiro como dado estruturado
(`extrair_afirmacoes`); o python-chess confere cada uma nas posições que a
explicação alcança (`conferir_afirmacoes`). Afirmação falsa vira `erro`
`afirmacao_falsa`, que dispara a rodada de correção como qualquer outro erro.
A conferência é pura: não toca em rede nem em banco."""
from __future__ import annotations

import logging

import chess

from chess_trainer.coach.costs import Uso
from chess_trainer.coach.llm import FERRAMENTA_FINAL, LlmClient
from chess_trainer.coach.verify import CASA_RE, TIPO_DA_PECA, Issue, _da_xeque, limpar_san

log = logging.getLogger(__name__)

TIPOS = ("ataca", "mais_atacantes", "indefesa", "cravada", "unico_lance", "unica_casa_do_rei",
         "garfo", "xeque", "mate", "peca_em_casa", "outro")
LADO = {"brancas": chess.WHITE, "pretas": chess.BLACK}
NOME_DO_LADO = {chess.WHITE: "as brancas", chess.BLACK: "as pretas"}
EFFORT_CHECAGEM = "low"
AVISO_SEM_FERRAMENTA = ("\n\nSua resposta anterior veio em texto, sem chamar a ferramenta. Chame a ferramenta com a lista "
                        "(vazia, se a explicação não fizer nenhuma afirmação sobre o tabuleiro).")
MAX_TOKENS_CHECAGEM = 4000

_CASA_OU_NULO = {"type": ["string", "null"], "description": "Casa do tabuleiro (a1–h8) ou nulo."}

# esquema estrito: toda propriedade em `required`, sem `minItems`/`maxItems` (a API recusa)
ESQUEMA_AFIRMACOES: dict = {
    "type": "object",
    "properties": {
        "afirmacoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": list(TIPOS),
                             "description": "ataca: a peça em `peca` ataca/apoia/defende/protege/cobre/controla a casa `alvo`. "
                                            "mais_atacantes: o lado `lado` ataca `alvo` mais vezes do que o outro defende. "
                                            "indefesa: a peça em `peca` não tem defensor. cravada: a peça em `peca` está cravada. "
                                            "unico_lance: `lance` é o único lance legal. unica_casa_do_rei: `lance` é o único lance do rei. "
                                            "garfo: a peça em `peca` ataca todas as `casas` de uma vez. xeque: `lance` dá xeque. "
                                            "mate: `lance` é mate. peca_em_casa: uma `tipo_peca` do lado `lado` está em `peca`. "
                                            "outro: o que não cabe em nenhum tipo."},
                    "trecho": {"type": "string", "description": "As palavras exatas da explicação que fazem a afirmação (curto)."},
                    "peca": {**_CASA_OU_NULO, "description": "Casa da peça de que a afirmação fala, ou nulo."},
                    "alvo": {**_CASA_OU_NULO, "description": "Casa atacada/defendida/disputada, ou nulo."},
                    "lance": {"type": ["string", "null"], "description": "Lance em SAN (ex.: Kh1, Qxg7#), ou nulo."},
                    "lado": {"type": ["string", "null"], "description": "`brancas` | `pretas`, ou nulo."},
                    "tipo_peca": {"type": ["string", "null"], "description": "`dama` | `torre` | `bispo` | `cavalo` | `peão` | `rei`, ou nulo."},
                    "casas": {"type": "array", "items": {"type": "string"},
                              "description": "As casas atacadas ao mesmo tempo (garfo); vazia quando não se aplica."},
                },
                "required": ["tipo", "trecho", "peca", "alvo", "lance", "lado", "tipo_peca", "casas"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["afirmacoes"],
    "additionalProperties": False,
}

SYSTEM_AFIRMACOES = f"""Você lê a explicação de um lance de xadrez e lista TODA afirmação verificável sobre o
tabuleiro, uma por item, sem julgar se é verdadeira. Traduza para casas:
- 'a dama de g4 ataca d4' → ataca peca=g4 alvo=d4;
- 'o cavalo de f5 e a dama de g4 atacam d4' → dois itens;
- 'as brancas atacam d4 mais vezes do que as pretas defendem' → mais_atacantes lado=brancas alvo=d4;
- 'Kh1 é a única casa do rei' → unica_casa_do_rei lance=Kh1;
- 'única defesa' / 'único lance' → unico_lance;
- 'apoiada pelo cavalo de f5' quando fala de Qxg7# → ataca peca=f5 alvo=g7 (o alvo é a casa de chegada
  do lance da frase);
- 'a torre de d8' (só a existência) → peca_em_casa.
O que não couber em nenhum tipo vai como `outro`. Entregue pela ferramenta `{FERRAMENTA_FINAL}`."""


def extrair_afirmacoes(llm: LlmClient, texto: str) -> tuple[list[dict], Uso, int]:
    """Pede ao segundo modelo a lista de afirmações do texto. Devolve (lista, uso, chamadas à
    API); sem resposta estruturada a lista vem vazia — nunca levanta por isso. `ErroDoTreinador`
    do cliente sobe como nas outras chamadas (a rota já o traduz)."""
    user = f"## Explicação\n{texto}\n\nListe as afirmações desta explicação."
    r = llm.run_agent(system=SYSTEM_AFIRMACOES, user=user, ferramentas=[], esquema_final=ESQUEMA_AFIRMACOES,
                      effort=EFFORT_CHECAGEM, max_tokens=MAX_TOKENS_CHECAGEM)
    uso, n = r.uso, r.n_chamadas_api
    if r.estruturado is None:
        # respondeu em texto em vez de chamar a ferramenta: uma segunda chance, com o aviso
        log.warning("checagem: o modelo respondeu sem a ferramenta (%r); pedindo de novo", r.texto[:200])
        r = llm.run_agent(system=SYSTEM_AFIRMACOES, user=user + AVISO_SEM_FERRAMENTA, ferramentas=[],
                          esquema_final=ESQUEMA_AFIRMACOES, effort=EFFORT_CHECAGEM, max_tokens=MAX_TOKENS_CHECAGEM)
        uso, n = uso + r.uso, n + r.n_chamadas_api
    itens = (r.estruturado or {}).get("afirmacoes")
    lista = [a for a in itens if isinstance(a, dict)] if isinstance(itens, list) else []
    log.info("checagem: %d afirmações extraídas%s", len(lista), "" if r.estruturado is not None else " (sem resposta estruturada)")
    return lista, uso, n


# --- conferência -------------------------------------------------------------

def _casa(valor: object) -> int | None:
    return chess.parse_square(valor) if isinstance(valor, str) and CASA_RE.match(valor) else None


def _san(valor: object) -> str | None:
    limpo = limpar_san(valor) if isinstance(valor, str) else ""
    return limpo or None


def _nomes(casas) -> str:
    return ", ".join(chess.square_name(c) for c in casas)


def _com_peca(boards: list[chess.Board], casa: int) -> list[chess.Board]:
    return [b for b in boards if b.piece_at(casa) is not None]


def _sem_peca(casa: int) -> str:
    return f"não há peça em {chess.square_name(casa)} em nenhuma posição da explicação"


def _primeira_com_peca(boards: list[chess.Board], casa: int) -> chess.Board:
    """A posição em que o motivo é calculado: a inicial quando a peça já está lá, senão a
    primeira em que ela aparece (a dama só chega a f2 depois de Qxf2+)."""
    return _com_peca(boards, casa)[0]


def _ataca(a: dict, boards: list[chess.Board]) -> str | None:
    peca, alvo = _casa(a.get("peca")), _casa(a.get("alvo"))
    if peca is None or alvo is None:
        return None
    if any(alvo in b.attacks(peca) for b in _com_peca(boards, peca)):
        return None
    if not _com_peca(boards, peca):
        return _sem_peca(peca)
    b = _primeira_com_peca(boards, peca)
    quem = b.attackers(b.piece_at(peca).color, alvo)
    de, para = chess.square_name(peca), chess.square_name(alvo)
    return f"{de} não ataca {para} (quem ataca {para}: {_nomes(quem)})" if quem else f"{de} não ataca {para} (ninguém ataca {para})"


def _mais_atacantes(a: dict, boards: list[chess.Board]) -> str | None:
    lado, alvo = LADO.get(a.get("lado")), _casa(a.get("alvo"))
    if lado is None or alvo is None:
        return None
    if any(len(b.attackers(lado, alvo)) > len(b.attackers(not lado, alvo)) for b in boards):
        return None
    b = boards[0]
    n_a, n_d = len(b.attackers(lado, alvo)), len(b.attackers(not lado, alvo))
    return (f"{NOME_DO_LADO[lado]} atacam {chess.square_name(alvo)} {n_a} {'vez' if n_a == 1 else 'vezes'} "
            f"e {NOME_DO_LADO[not lado]} defendem {n_d}")


def _indefesa(a: dict, boards: list[chess.Board]) -> str | None:
    peca = _casa(a.get("peca"))
    if peca is None:
        return None
    if any(not b.attackers(b.piece_at(peca).color, peca) for b in _com_peca(boards, peca)):
        return None
    if not _com_peca(boards, peca):
        return _sem_peca(peca)
    b = _primeira_com_peca(boards, peca)
    return f"a peça de {chess.square_name(peca)} não está indefesa: defendida por {_nomes(b.attackers(b.piece_at(peca).color, peca))}"


def _cravada(a: dict, boards: list[chess.Board]) -> str | None:
    peca = _casa(a.get("peca"))
    if peca is None:
        return None
    if any(b.is_pinned(b.piece_at(peca).color, peca) for b in _com_peca(boards, peca)):
        return None
    return _sem_peca(peca) if not _com_peca(boards, peca) else f"a peça de {chess.square_name(peca)} não está cravada"


def _lances_legais(b: chess.Board, *, do_rei: bool) -> list[chess.Move]:
    return [m for m in b.legal_moves if not do_rei or b.piece_type_at(m.from_square) == chess.KING]


def _unico(a: dict, boards: list[chess.Board], *, do_rei: bool) -> str | None:
    """`unico_lance` (todos os lances) e `unica_casa_do_rei` (só os do rei): o lance é o único
    legal em alguma posição. O motivo sai da primeira posição em que o lance é legal."""
    san = _san(a.get("lance"))
    if san is None:
        return None
    onde: list[tuple[chess.Board, chess.Move]] = []
    for b in boards:
        try:
            onde.append((b, b.parse_san(san)))
        except ValueError:
            continue
    o_que = "o único lance do rei" if do_rei else "o único lance"
    if not onde:
        return f"{san} não é legal em nenhuma posição da explicação"
    for b, mv in onde:
        if do_rei and b.piece_type_at(mv.from_square) != chess.KING:
            continue
        if _lances_legais(b, do_rei=do_rei) == [mv]:
            return None
    b, mv = onde[0]
    if do_rei and b.piece_type_at(mv.from_square) != chess.KING:
        return f"{san} não é lance do rei"
    outros = [b.san(m) for m in _lances_legais(b, do_rei=do_rei) if m != mv]
    return f"{san} não é {o_que}: também {', '.join(outros[:3])}"


def _garfo(a: dict, boards: list[chess.Board]) -> str | None:
    peca = _casa(a.get("peca"))
    casas = [c for c in (_casa(x) for x in (a.get("casas") or [])) if c is not None] if isinstance(a.get("casas"), list) else []
    if peca is None or len(casas) < 2:
        return None
    if any(all(c in b.attacks(peca) for c in casas) for b in _com_peca(boards, peca)):
        return None
    if not _com_peca(boards, peca):
        return _sem_peca(peca)
    b = _primeira_com_peca(boards, peca)
    fora = [c for c in casas if c not in b.attacks(peca)]
    return f"{chess.square_name(peca)} não ataca {_nomes(fora)}"


def _xeque_ou_mate(a: dict, boards: list[chess.Board], *, mate: bool) -> str | None:
    san = _san(a.get("lance"))
    if san is None:
        return None
    if _da_xeque(boards, san, mate=mate):
        return None
    return f"{san} não é mate em nenhuma posição da explicação" if mate else f"{san} não dá xeque em nenhuma posição da explicação"


def _peca_em_casa(a: dict, boards: list[chess.Board]) -> str | None:
    peca, tipo = _casa(a.get("peca")), TIPO_DA_PECA.get(str(a.get("tipo_peca") or "").lower())
    lado_txt = a.get("lado")
    lado = LADO.get(lado_txt) if lado_txt is not None else None
    if peca is None or tipo is None or (lado_txt is not None and lado is None):
        return None
    for b in boards:
        p = b.piece_at(peca)
        if p is not None and p.piece_type == tipo and (lado is None or p.color == lado):
            return None
    de_quem = f" das {lado_txt}" if lado is not None else ""
    return f"não há {a['tipo_peca']}{de_quem} em {chess.square_name(peca)} em nenhuma posição da explicação"


def _motivo(a: dict, boards: list[chess.Board]) -> str | None:
    """None quando a afirmação vale em pelo menos uma posição, ou quando não dá para conferir."""
    tipo = a.get("tipo")
    if tipo == "ataca":
        return _ataca(a, boards)
    if tipo == "mais_atacantes":
        return _mais_atacantes(a, boards)
    if tipo == "indefesa":
        return _indefesa(a, boards)
    if tipo == "cravada":
        return _cravada(a, boards)
    if tipo == "unico_lance":
        return _unico(a, boards, do_rei=False)
    if tipo == "unica_casa_do_rei":
        return _unico(a, boards, do_rei=True)
    if tipo == "garfo":
        return _garfo(a, boards)
    if tipo in ("xeque", "mate"):
        return _xeque_ou_mate(a, boards, mate=tipo == "mate")
    if tipo == "peca_em_casa":
        return _peca_em_casa(a, boards)
    return None  # `outro` e tipos desconhecidos


def conferir_afirmacoes(afirmacoes: list[dict], alcancaveis: list[chess.Board]) -> list[Issue]:
    """Uma afirmação vale se é verdade em PELO MENOS UMA posição alcançável (a mesma semântica
    permissiva das regras 4 e 7 do verificador). Falsa → `erro` `afirmacao_falsa` com o trecho
    e um motivo concreto. Campo malformado ou tipo `outro`: ignorado em silêncio."""
    if not alcancaveis:
        return []
    achados: dict[str, Issue] = {}
    for a in afirmacoes:
        if not isinstance(a, dict):
            continue
        motivo = _motivo(a, alcancaveis)
        if motivo is None:
            continue
        detalhe = f"«{str(a.get('trecho') or '').strip()}»: {motivo}"
        achados.setdefault(detalhe, Issue("afirmacao_falsa", "erro", detalhe))
    return list(achados.values())
