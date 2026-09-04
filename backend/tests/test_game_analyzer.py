import chess
import pytest

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.analysis.game_analyzer import analyze_game
from chess_trainer.core.evals import MATE_SCORE
from tests.fakes import FakeEngine, first_legal_default

SCHOLAR = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


def test_one_entry_per_ply_and_sign_flip():
    board = chess.Board()
    after_e4 = chess.Board(); after_e4.push_uci("e2e4")
    fake = FakeEngine({
        board.epd(): [LineEval("e2e4", 30, ("e2e4",))],
        after_e4.epd(): [LineEval("e7e5", -25, ("e7e5",))],
    }, first_legal_default(0))
    data = analyze_game(SCHOLAR, fake, depth=8)
    assert len(data) == 7
    assert data[0].ply == 1 and data[0].move_played == "e4" and data[0].move_uci == "e2e4"
    assert data[0].fen == chess.STARTING_FEN
    assert data[0].eval_before == 30 and data[0].best_move == "e2e4" and data[0].best_eval == 30
    assert data[0].eval_after == 25  # -(-25): POV das brancas após e4
    assert data[1].eval_before == -25 and data[1].move_played == "e5"


def test_terminal_position_uses_mate_score_without_engine():
    fake = FakeEngine(default=first_legal_default(0))
    data = analyze_game(SCHOLAR, fake, depth=8)
    last = data[-1]
    assert last.move_played == "Qxf7#"
    assert last.eval_after == MATE_SCORE  # brancas deram mate
    final = chess.Board()
    for d in data:
        final.push_uci(d.move_uci)
    assert final.epd() not in fake.calls


def test_engine_called_once_per_position():
    fake = FakeEngine(default=first_legal_default(0))
    analyze_game(SCHOLAR, fake, depth=8)
    assert len(fake.calls) == 7  # 8 posições, a última é terminal


def test_empty_pgn_raises():
    with pytest.raises(ValueError):
        analyze_game('[Event "x"]\n\n*', FakeEngine(), depth=8)


def test_empty_engine_output_on_live_position_raises():
    import chess.engine
    fake = FakeEngine(default=lambda board: [])
    with pytest.raises(chess.engine.EngineError):
        analyze_game(SCHOLAR, fake, depth=8)
