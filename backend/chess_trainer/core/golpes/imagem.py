"""O golpe desenhado: setas verdes para os lances de quem soluciona, vermelhas para o que eles
descobrem ou atacam, casas de chegada marcadas e o rei adversário realçado quando o golpe é
contra ele (spec golpes §6.1)."""
from __future__ import annotations

from typing import Sequence

import chess
import chess.svg

from chess_trainer.core.golpes.assinatura import anotar

VERDE = "#15803d"
VERMELHO = "#b91c1c"
# realce das casas da assinatura: cor translúcida por baixo da peça. O `squares=` do chess.svg
# desenha um X por cima, e um X no rei adversário lia como "riscado", "capturado" ou "mate"
COR_REI = "#f59e0b99"       # âmbar: o rei adversário, só quando algum lance dá xeque ou mate
COR_CHEGADA = "#15803d55"   # verde claro: as casas de chegada dos lances de quem soluciona


def svg_do_golpe(fen: str, lances_uci: Sequence[str], tamanho: int = 400) -> str:
    board = chess.Board(fen)
    a = anotar(board, lances_uci)
    setas = []
    # a casa do rei faz parte da assinatura sempre, mas no desenho ela só ensina quando o golpe
    # passa por ele; num final de torres o rei realçado sugeria uma participação que não existe
    cores = {chess.parse_square(a.rei): COR_REI} if any(l.xeque for l in a.lances) else {}
    for l in a.lances:
        setas.append(chess.svg.Arrow(chess.parse_square(l.origem), chess.parse_square(l.destino), color=VERDE))
        cores.setdefault(chess.parse_square(l.destino), COR_CHEGADA)
        for _peca, casa, por in l.descobertas:
            setas.append(chess.svg.Arrow(chess.parse_square(por), chess.parse_square(casa), color=VERMELHO))
        for _peca, casa in l.ataques:
            setas.append(chess.svg.Arrow(chess.parse_square(l.destino), chess.parse_square(casa), color=VERMELHO))
    return chess.svg.board(board, orientation=board.turn, arrows=setas, fill=cores, size=tamanho)
