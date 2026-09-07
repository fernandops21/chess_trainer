from dataclasses import dataclass, field

import chess

from chess_trainer.core.models import LichessPuzzle
from chess_trainer.core.tactics.themes import primary_theme

LICHESS_TRAINING_URL = "https://lichess.org/training/{id}"


@dataclass
class Tactic:
    id: str
    fen_start: str
    side_to_move: str
    solution: dict
    end_reason: str
    theme: str
    themes: list[str]
    rating: int
    solver_moves: int
    lichess_url: str
    #: posição de antes do lance do adversário (o FEN da linha do Lichess) e o lance em si:
    #: a interface abre nela e anima o lance antes de liberar as peças
    fen_before: str
    last_move: str
    kind: str = "tactic"
    category: str = "lichess"
    popularity: int = 0
    nb_plays: int = 0
    opening_tags: list[str] = field(default_factory=list)


def to_tactic(row: LichessPuzzle) -> Tactic:
    """Aplica o lance do adversário e monta a solução no formato dos puzzles próprios.

    Levanta ValueError se algum lance for ilegal (linha corrompida)."""
    try:
        board = chess.Board(row.fen)
    except ValueError as exc:
        raise ValueError(f"puzzle {row.id}: FEN inválido") from exc
    ucis = row.moves.split()
    if len(ucis) < 2:
        raise ValueError(f"puzzle {row.id}: menos de dois lances")
    _push(board, ucis[0], row.id)
    fen_start = board.fen()
    side = "white" if board.turn == chess.WHITE else "black"
    moves = []
    for i, uci in enumerate(ucis[1:]):
        _push(board, uci, row.id)
        moves.append({"uci": uci, "by": "solver" if i % 2 == 0 else "engine", "alternatives": []})
    end_reason = "mate" if board.is_checkmate() else "material_gain"
    themes = row.theme_list
    return Tactic(
        id=row.id, fen_start=fen_start, side_to_move=side,
        solution={"moves": moves, "explanation_pv": []}, end_reason=end_reason,
        theme=primary_theme(themes), themes=themes, rating=row.rating,
        solver_moves=sum(1 for m in moves if m["by"] == "solver"),
        lichess_url=LICHESS_TRAINING_URL.format(id=row.id),
        fen_before=row.fen, last_move=ucis[0],
        popularity=row.popularity, nb_plays=row.nb_plays,
        opening_tags=row.opening_tags.split() if row.opening_tags else [],
    )


def _push(board: chess.Board, uci: str, puzzle_id: str) -> None:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise ValueError(f"puzzle {puzzle_id}: lance inválido {uci}") from exc
    if move not in board.legal_moves:
        raise ValueError(f"puzzle {puzzle_id}: lance ilegal {uci} em {board.fen()}")
    board.push(move)
