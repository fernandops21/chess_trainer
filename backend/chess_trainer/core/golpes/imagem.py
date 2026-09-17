"""O golpe desenhado: setas verdes para os lances de quem soluciona, vermelhas para o que eles
descobrem ou atacam, rei adversário e casas de chegada marcadas (spec golpes §6.1)."""
from __future__ import annotations

from typing import Sequence

import chess
import chess.svg

from chess_trainer.core.golpes.assinatura import anotar

VERDE = "#15803d"
VERMELHO = "#b91c1c"


def svg_do_golpe(fen: str, lances_uci: Sequence[str], tamanho: int = 400) -> str:
    board = chess.Board(fen)
    a = anotar(board, lances_uci)
    setas = []
    casas = chess.SquareSet([chess.parse_square(a.rei)])
    for l in a.lances:
        setas.append(chess.svg.Arrow(chess.parse_square(l.origem), chess.parse_square(l.destino), color=VERDE))
        casas.add(chess.parse_square(l.destino))
        for _peca, casa, por in l.descobertas:
            setas.append(chess.svg.Arrow(chess.parse_square(por), chess.parse_square(casa), color=VERMELHO))
        for _peca, casa in l.ataques:
            setas.append(chess.svg.Arrow(chess.parse_square(l.destino), chess.parse_square(casa), color=VERMELHO))
    return chess.svg.board(board, orientation=board.turn, arrows=setas, squares=casas, size=tamanho)
