import chess

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.puzzles.generator import PuzzleConfig, generate_avoid
from tests.fakes import FakeEngine

CFG = PuzzleConfig(depth=10, avoid_gap_cp=150)
FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"


def test_avoid_generated_when_gap_is_large():
    pv = ("f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7", "f1e1", "b7b5")
    fake = FakeEngine({chess.Board(FEN).epd(): [LineEval("f1b5", 320, pv), LineEval("d2d3", 100, ("d2d3",))]})
    draft = generate_avoid(chess.Board(FEN), fake, CFG)
    assert draft is not None
    assert draft.end_reason == "explanation" and draft.solver_moves == 1
    assert [(m.uci, m.by) for m in draft.moves] == [("f1b5", "solver")]
    assert draft.explanation_pv == list(pv[:6])
    assert draft.side_to_move == "white" and draft.fen_start == FEN


def test_avoid_not_generated_when_gap_is_small():
    fake = FakeEngine({chess.Board(FEN).epd(): [LineEval("f1b5", 320, ("f1b5",)), LineEval("d2d3", 200, ("d2d3",))]})
    assert generate_avoid(chess.Board(FEN), fake, CFG) is None


def test_avoid_not_generated_with_single_line():
    fake = FakeEngine({chess.Board(FEN).epd(): [LineEval("f1b5", 320, ("f1b5",))]})
    assert generate_avoid(chess.Board(FEN), fake, CFG) is None


def test_avoid_not_generated_when_best_is_the_move_played():
    """Se o melhor lance é justamente o que foi jogado, não há o que evitar."""
    pv = ("f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7")
    fake = FakeEngine({chess.Board(FEN).epd(): [LineEval("f1b5", 320, pv), LineEval("d2d3", 100, ("d2d3",))]})
    assert generate_avoid(chess.Board(FEN), fake, CFG, played_uci="f1b5") is None
    assert generate_avoid(chess.Board(FEN), fake, CFG, played_uci="d2d4") is not None
