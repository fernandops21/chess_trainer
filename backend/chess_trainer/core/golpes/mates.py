"""Padrões de mate nomeados (spec golpes design §3.6): detecta o mate sufocado, o mate árabe
e o mate do corredor na posição final do exercício do usuário, pelo mesmo nome que o Lichess
usa em `lichess_puzzle_themes` — assim os irmãos deste degrau da cascata (`padrao-mate`,
spec §5) vêm direto da etiqueta do Lichess, sem precisar de assinatura.

Só estes três padrões foram aprovados. Medido (script de leitura em
`evals/golpes/medir_mates.py`) contra as 242 413 mates do Lichess: sufocado (recall 100%,
precisão 100%), árabe (recall 100%, precisão 77% — sobra pillsbury/vukovic/canto sem
etiqueta) e corredor (recall 100%, precisão 26%, tolerando uma casa vazia coberta — o resto é corredor estrutural que o
Lichess deixou sem etiqueta). Protótipos de dovetail, epaulette e boden NÃO bateram com a
definição do Lichess e ficam de fora; um detector novo só entra com recall ≥ 95% contra a
etiqueta do Lichess, com as sobras inspecionadas à mão (mesma régua do script de medição).

Puro: só python-chess."""
from __future__ import annotations

from typing import Callable, Sequence

import chess


def vizinhas(sq: int) -> list[int]:
    """Casas ao redor de `sq`, dentro do tabuleiro."""
    f, r = chess.square_file(sq), chess.square_rank(sq)
    return [chess.square(f + df, r + dr) for df in (-1, 0, 1) for dr in (-1, 0, 1)
            if (df or dr) and 0 <= f + df < 8 and 0 <= r + dr < 8]


def corredor(b: chess.Board, rei: int, dono: chess.Color, xeques: list[int]) -> bool:
    """Mate do corredor: rei preso na própria última fila, torre ou dama dando xeque nela, e as
    casas à frente do rei (fora da última fila) bloqueadas por peças suas — tolerando UMA casa
    vazia desde que o adversário a cubra. O caso real que motivou o degrau é assim: peões em f7 e
    g7, h7 vazia (o peão foi a h6) e coberta pela dama de longe; para o jogador continua sendo
    mate do corredor. Exigir as três casas ocupadas deixava esse exercício sem padrão; aceitar
    qualquer número de casas só cobertas vira "qualquer mate na última fila" (65 mil puzzles)."""
    fila_casa = 0 if dono == chess.WHITE else 7
    if chess.square_rank(rei) != fila_casa:
        return False
    if not any(b.piece_type_at(x) in (chess.ROOK, chess.QUEEN) and chess.square_rank(x) == fila_casa for x in xeques):
        return False
    frente = [s for s in vizinhas(rei) if chess.square_rank(s) != fila_casa]
    proprias = [s for s in frente if (p := b.piece_at(s)) is not None and p.color == dono]
    livres = [s for s in frente if s not in proprias]
    return bool(proprias) and len(livres) <= 1 and all(b.is_attacked_by(not dono, s) for s in livres)


def sufocado(b: chess.Board, rei: int, dono: chess.Color, xeques: list[int]) -> bool:
    """Mate sufocado: xeque de cavalo só, todas as casas ao redor do rei ocupadas por peças
    suas (nenhuma casa livre para fugir nem bloquear)."""
    if len(xeques) != 1 or b.piece_type_at(xeques[0]) != chess.KNIGHT:
        return False
    return all((p := b.piece_at(s)) is not None and p.color == dono for s in vizinhas(rei))


def arabe(b: chess.Board, rei: int, dono: chess.Color, xeques: list[int]) -> bool:
    """Mate árabe: rei no canto, torre adjacente dando xeque e protegida por um cavalo."""
    if rei not in (chess.A1, chess.H1, chess.A8, chess.H8):
        return False
    if len(xeques) != 1 or b.piece_type_at(xeques[0]) != chess.ROOK:
        return False
    t = xeques[0]
    if chess.square_distance(t, rei) != 1:
        return False
    return any(b.piece_type_at(a) == chess.KNIGHT for a in b.attackers(not dono, t))


# do mais específico ao mais geral: quando uma posição bate com mais de um (ex.: um mate
# árabe cujo canto também é a última fila da torre), fica o mais específico
PADROES: tuple[tuple[str, Callable[[chess.Board, int, chess.Color, list[int]], bool]], ...] = (
    ("smotheredMate", sufocado),
    ("arabianMate", arabe),
    ("backRankMate", corredor),
)

NOME_PT = {"smotheredMate": "mate sufocado", "arabianMate": "mate árabe", "backRankMate": "mate do corredor"}


def _detectados(board: chess.Board, detectores) -> list[str]:
    if not board.is_checkmate():
        return []
    dono = board.turn
    rei = board.king(dono)
    xeques = list(board.checkers())
    return [nome for nome, detector in detectores if detector(board, rei, dono, xeques)]


def padroes_de_mate(board: chess.Board) -> list[str]:
    """TODOS os padrões aprovados (de `PADROES`, do mais específico ao mais geral) que a posição
    de xeque-mate satisfaz: as etiquetas não se excluem — um mate árabe na última fila atrás dos
    próprios peões também é corredor, como no Lichess, em que um puzzle leva vários temas."""
    return _detectados(board, PADROES)


def padrao_de_mate(board: chess.Board) -> str | None:
    """O mais específico dos `padroes_de_mate`, ou `None`."""
    achados = padroes_de_mate(board)
    return achados[0] if achados else None


def corredor_apertado(b: chess.Board, rei: int, dono: chess.Color, xeques: list[int]) -> bool:
    """Mate do corredor, versão APERTADA: gera etiqueta própria para puzzles do Lichess que ele
    não etiquetou (spec golpes design §3.6, "etiquetas próprias"), nunca classifica o exercício
    do usuário (isso continua com `corredor`, que tolera uma casa vazia coberta). Rei na própria
    última fila; torre ou dama dando xeque nela, sem estar adjacente ao rei (`square_distance ==
    1`, que seria outro padrão); as casas à frente do rei (fora da última fila) formam uma lista
    não vazia e TODAS ocupadas por PEÕES da própria cor — sem tolerância nenhuma, ao contrário de
    `corredor`.

    Medido contra as 242 413 mates do Lichess (`evals/golpes/medir_mates.py`): recall 93,8% da
    etiqueta `backRankMate` (12 004/12 802) e 4 451 extras sem etiqueta — amostra inspecionada à
    mão, textbook (`Qe8#` contra f7/g7/h7, `Rf8#` com o rei em h8 atrás de g7/h7). A regra frouxa
    (qualquer peça própria à frente, sem exigir peão) achava o dobro de extras, mas metade era
    outra ideia (uma torre presa por cravada na frente do rei, não um corredor); por isso a
    exigência de peão."""
    fila_casa = 0 if dono == chess.WHITE else 7
    if chess.square_rank(rei) != fila_casa:
        return False
    checadores = [x for x in xeques if b.piece_type_at(x) in (chess.ROOK, chess.QUEEN)
                 and chess.square_rank(x) == fila_casa]
    if not checadores or any(chess.square_distance(x, rei) == 1 for x in checadores):
        return False
    frente = [s for s in vizinhas(rei) if chess.square_rank(s) != fila_casa]
    if not frente:
        return False
    return all((p := b.piece_at(s)) is not None and p.piece_type == chess.PAWN and p.color == dono for s in frente)


# detectores ainda não aprovados para o produto (não entram em `PADROES`/`padrao_de_mate`): só
# geram etiqueta própria em `lichess_puzzle_padroes` (`preparar_padroes`, spec golpes design
# §3.6/§4) para puzzles do Lichess que ele mesmo não etiquetou. Um detector novo só entra aqui
# depois da mesma régua de aprovação (recall ≥ 95%, sobras inspecionadas à mão)
PADROES_PARA_CANDIDATOS: tuple[tuple[str, Callable[[chess.Board, int, chess.Color, list[int]], bool]], ...] = (
    ("backRankMate", corredor_apertado),
)

# versão da régua de `padrao_para_candidato`: sobe quando um detector candidato muda ou entra;
# `preparar_padroes` refaz a tabela inteira quando a versão gravada em `settings` não bate
VERSAO_PADROES = 1


def padroes_para_candidato(board: chess.Board) -> list[str]:
    """Como `padroes_de_mate`, mas com os detectores candidatos (`PADROES_PARA_CANDIDATOS`), que
    geram etiqueta PRÓPRIA em vez de classificar o exercício do usuário: hoje só o corredor
    apertado."""
    return _detectados(board, PADROES_PARA_CANDIDATOS)


def padrao_para_candidato(board: chess.Board) -> str | None:
    achados = padroes_para_candidato(board)
    return achados[0] if achados else None


def padroes_do_exercicio(fen: str, lances_uci: Sequence[str]) -> tuple[list[str], int] | None:
    """Joga a solução inteira a partir de `fen`; quando ela termina em xeque-mate com ao menos um
    padrão aprovado, devolve `(temas, quantos lances quem soluciona jogou)`, os temas do mais
    específico ao mais geral. `None` sem mate, sem padrão aprovado, FEN inválida ou lance ilegal —
    nunca levanta (degrau opcional da cascata, spec §5)."""
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    if not board.is_valid():
        return None
    n_lances = 0
    for i, uci in enumerate(lances_uci):
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            return None
        if not board.is_legal(mv):
            return None
        board.push(mv)
        if i % 2 == 0:
            n_lances += 1
    temas = padroes_de_mate(board)
    return (temas, n_lances) if temas else None


def padrao_do_exercicio(fen: str, lances_uci: Sequence[str]) -> tuple[str, int] | None:
    """Só o padrão mais específico de `padroes_do_exercicio`."""
    achado = padroes_do_exercicio(fen, lances_uci)
    return None if achado is None else (achado[0][0], achado[1])
