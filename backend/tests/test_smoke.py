import chess
import chess_trainer


def test_package_imports():
    assert chess_trainer.__version__ == "0.1.0"
    assert chess.Board().fen().startswith("rnbqkbnr")
