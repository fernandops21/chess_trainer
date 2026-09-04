from datetime import datetime

from chess_trainer.core.models import Game, Puzzle
from tests.test_models import _game


def make_puzzle(db, *, fen: str, category="rapid", theme="tactic", kind="punish", side="white",
                played_at=datetime(2026, 8, 1), due_at=None, is_leech=False, game: Game | None = None) -> Puzzle:
    if game is None:
        game = _game(source_id=f"src-{fen}", category=category, played_at=played_at)
        db.add(game)
        db.flush()
    from chess_trainer.core.models import Position
    pos = Position(game_id=game.id, ply=1, fen=fen, move_played="x", move_uci="a2a3",
                   eval_before=0, eval_after=-300, best_move="a2a4", best_eval=0,
                   is_mistake=True, mistake_level="blunder", mistake_by="opponent")
    db.add(pos)
    db.flush()
    puzzle = Puzzle(position_id=pos.id, game_id=game.id, kind=kind, fen_start=fen, side_to_move=side,
                    solution='{"moves": [{"uci": "a2a4", "by": "solver", "alternatives": []}], "explanation_pv": []}',
                    end_reason="material_gain", theme=theme, category=category, solver_moves=1,
                    is_leech=is_leech, srs_due_at=due_at)
    db.add(puzzle)
    db.commit()
    return puzzle
