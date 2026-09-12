import json
from datetime import datetime

from chess_trainer.core.models import Game, Puzzle
from tests.test_models import _game

SOLUCAO_PADRAO = '{"moves": [{"uci": "a2a4", "by": "solver", "alternatives": []}], "explanation_pv": []}'


def make_puzzle(db, *, fen: str, category="rapid", theme="tactic", kind="punish", side="white",
                played_at=datetime(2026, 8, 1), due_at=None, is_leech=False, game: Game | None = None,
                solution: dict | None = None, move_played="x", move_uci="a2a3", ply=1,
                mistake_by="opponent") -> Puzzle:
    if game is None:
        game = _game(source_id=f"src-{fen}", category=category, played_at=played_at)
        db.add(game)
        db.flush()
    from chess_trainer.core.models import Position
    pos = Position(game_id=game.id, ply=ply, fen=fen, move_played=move_played, move_uci=move_uci,
                   eval_before=0, eval_after=-300, best_move="a2a4", best_eval=0,
                   is_mistake=True, mistake_level="blunder", mistake_by=mistake_by)
    db.add(pos)
    db.flush()
    solver_moves = sum(1 for m in solution["moves"] if m.get("by") == "solver") if solution else 1
    puzzle = Puzzle(position_id=pos.id, game_id=game.id, kind=kind, fen_start=fen, side_to_move=side,
                    solution=json.dumps(solution) if solution else SOLUCAO_PADRAO,
                    end_reason="material_gain", theme=theme, category=category, solver_moves=solver_moves,
                    is_leech=is_leech, srs_due_at=due_at)
    db.add(puzzle)
    db.commit()
    return puzzle
