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


HANGING_QUEEN_FEN = "3qk3/8/8/8/8/2N5/8/4K3 b - - 0 1"  # ...Qd5?? indefesa, atacada pelo Nc3
DEFENDED_QUEEN_FEN = "3qk3/8/2p5/8/8/2N5/8/4K3 b - - 0 1"  # ...Qd5?? defendida, mas Nc3 (mais barato) ataca
HANGING_PAWN_FEN = "4k3/4p3/8/8/8/3N4/8/4K3 b - - 0 1"  # ...e5?? peão indefeso atacado pelo Nd3


def test_trivial_hanging_queen_is_not_generated():
    pos = _pos(fen=HANGING_QUEEN_FEN, move_uci="d8d5", eval_after=-900)
    fake = FakeEngine()
    assert build_drafts(pos, fake, CFG) == []
    assert fake.calls == []


def test_trivial_rule_yields_to_mate_for_solver():
    pos = _pos(fen=HANGING_QUEEN_FEN, move_uci="d8d5", eval_after=-(MATE_SCORE - 2))
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []


def test_defended_queen_with_cheap_attacker_is_trivial():
    pos = _pos(fen=DEFENDED_QUEEN_FEN, move_uci="d8d5", eval_after=-900)
    fake = FakeEngine()
    assert build_drafts(pos, fake, CFG) == []
    assert fake.calls == []


def test_hanging_pawn_is_not_trivial():
    pos = _pos(fen=HANGING_PAWN_FEN, move_uci="e7e5", eval_after=-300)
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []
