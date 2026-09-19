"""Padrões de mate nomeados (spec golpes design §3.6): detecta o mate sufocado, o mate árabe
e o mate do corredor na posição final do exercício do usuário, pelo mesmo nome que o Lichess
usa em `lichess_puzzle_themes` — assim os irmãos deste degrau da cascata (`padrao-mate`,
spec §5) vêm direto da etiqueta do Lichess, sem precisar de assinatura.

Só estes três padrões foram aprovados. Medido (script de leitura em
`evals/golpes/medir_mates.py`) contra as 242 413 mates do Lichess: sufocado (recall 100%,
precisão 100%), árabe (recall 100%, precisão 77% — sobra pillsbury/vukovic/canto sem
etiqueta) e corredor (recall 100%, precisão 58% — o resto é corredor estrutural que o
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
    """Mate do corredor: rei preso na própria última fila, torre ou dama dando xeque nela,
    e as casas à frente do rei (fora da última fila) todas ocupadas por peças suas."""
    fila_casa = 0 if dono == chess.WHITE else 7
    if chess.square_rank(rei) != fila_casa:
        return False
    if not any(b.piece_type_at(x) in (chess.ROOK, chess.QUEEN) and chess.square_rank(x) == fila_casa for x in xeques):
        return False
    frente = [s for s in vizinhas(rei) if chess.square_rank(s) != fila_casa]
    return bool(frente) and all((p := b.piece_at(s)) is not None and p.color == dono for s in frente)


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


def padrao_de_mate(board: chess.Board) -> str | None:
    """O primeiro padrão aprovado (de `PADROES`, do mais específico) que a posição de xeque-mate
    satisfaz; `None` fora do xeque-mate ou sem padrão nomeado nela."""
    if not board.is_checkmate():
        return None
    dono = board.turn
    rei = board.king(dono)
    xeques = list(board.checkers())
    for nome, detector in PADROES:
        if detector(board, rei, dono, xeques):
            return nome
    return None


def padrao_do_exercicio(fen: str, lances_uci: Sequence[str]) -> tuple[str, int] | None:
    """Joga a solução inteira a partir de `fen`; quando ela termina em xeque-mate com um padrão
    aprovado, devolve `(tema, quantos lances quem soluciona jogou)`. `None` sem mate, sem padrão
    aprovado, FEN inválida ou lance ilegal — nunca levanta (degrau opcional da cascata, spec §5)."""
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
    tema = padrao_de_mate(board)
    return None if tema is None else (tema, n_lances)
