import chess

from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import Position
from chess_trainer.core.puzzles.generator import PuzzleConfig
from chess_trainer.core.puzzles.service import build_drafts
from tests.fakes import FakeEngine, first_legal_default

CFG = PuzzleConfig(depth=10)


def _pos(**overrides) -> Position:
    defaults = dict(
        game_id="g1", ply=1, fen=chess.STARTING_FEN, move_played="e4", move_uci="e2e4",
        eval_before=0, eval_after=-50, best_move="e2e4", best_eval=0,
        is_mistake=True, mistake_level="mistake", mistake_by="opponent",
    )
    defaults.update(overrides)
    return Position(**defaults)


def test_prefilter_skips_engine_when_solver_eval_is_low():
    pos = _pos(eval_after=-50)
    fake = FakeEngine()
    drafts = build_drafts(pos, fake, CFG)
    assert drafts == []
    assert fake.calls == []


def test_prefilter_allows_engine_when_mate_for_solver():
    pos = _pos(eval_after=-(MATE_SCORE - 2))
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []
