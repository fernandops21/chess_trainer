import io
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn

from chess_trainer.core.analysis.engine import EngineLike, terminal_score


@dataclass
class PositionData:
    ply: int
    fen: str
    move_played: str
    move_uci: str
    eval_before: int
    eval_after: int
    best_move: str | None
    best_eval: int


def _evaluate(
    board: chess.Board, engine: EngineLike, depth: int, max_seconds: float | None,
) -> tuple[int, str | None]:
    term = terminal_score(board)
    if term is not None:
        return term, None
    lines = engine.analyse(board, depth, multipv=1, max_seconds=max_seconds)
    if not lines:
        raise chess.engine.EngineError("engine não devolveu linhas para uma posição não terminal")
    return lines[0].score, lines[0].move


def analyze_game(
    pgn: str, engine: EngineLike, depth: int, max_seconds: float | None = 15.0,
) -> list[PositionData]:
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("PGN inválido")
    moves = list(game.mainline_moves())
    if not moves:
        raise ValueError("PGN sem lances")

    board = game.board()
    scores: list[int] = []
    bests: list[str | None] = []
    fens: list[str] = []
    sans: list[str] = []
    for move in moves:
        score, best = _evaluate(board, engine, depth, max_seconds)
        scores.append(score)
        bests.append(best)
        fens.append(board.fen())
        sans.append(board.san(move))
        board.push(move)
    final_score, _ = _evaluate(board, engine, depth, max_seconds)
    scores.append(final_score)

    return [
        PositionData(
            ply=i + 1,
            fen=fens[i],
            move_played=sans[i],
            move_uci=moves[i].uci(),
            eval_before=scores[i],
            eval_after=-scores[i + 1],
            best_move=bests[i],
            best_eval=scores[i],
        )
        for i in range(len(moves))
    ]
