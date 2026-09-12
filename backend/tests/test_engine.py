import os

import chess
import chess.engine
import pytest

from chess_trainer.core.analysis.engine import (
    LineEval, StockfishEngine, find_stockfish, terminal_score,
)
from chess_trainer.core.analysis.interactive import InteractiveAnalyzer
from chess_trainer.core.evals import MATE_SCORE, is_mate_for
from tests.fakes import FakeEngine, first_legal_default


def test_terminal_score():
    mated = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert mated.is_checkmate()
    assert terminal_score(mated) == -MATE_SCORE
    stalemate = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert stalemate.is_stalemate()
    assert terminal_score(stalemate) == 0
    assert terminal_score(chess.Board()) is None


def test_fake_engine_script_then_default():
    board = chess.Board()
    fake = FakeEngine({board.epd(): [LineEval("e2e4", 30, ("e2e4", "e7e5"))]}, first_legal_default(0))
    assert fake.analyse(board, 10)[0].move == "e2e4"
    board.push_uci("e2e4")
    assert fake.analyse(board, 10)[0].score == 0
    assert len(fake.calls) == 2


def test_fake_engine_raises_without_script():
    with pytest.raises(KeyError):
        FakeEngine().analyse(chess.Board(), 10)


def test_fake_engine_records_max_seconds():
    board = chess.Board()
    fake = FakeEngine({board.epd(): [LineEval("e2e4", 30, ("e2e4",))]})
    fake.analyse(board, 10, max_seconds=5.0)
    assert fake.max_seconds == [5.0]
    fake.analyse(board, 10)
    assert fake.max_seconds == [5.0, None]


class _TimeoutStub:
    def analyse(self, board, limit, multipv=1):
        raise TimeoutError("sem resposta")


def test_stockfish_analyse_restarts_and_raises_engine_error_on_timeout(monkeypatch):
    restart_calls: list[bool] = []
    engine = StockfishEngine.__new__(StockfishEngine)
    engine._engine = _TimeoutStub()
    monkeypatch.setattr(engine, "restart", lambda: restart_calls.append(True))
    with pytest.raises(chess.engine.EngineError):
        engine.analyse(chess.Board(), depth=10, max_seconds=1.0)
    assert restart_calls == [True]


class _TransportSpy:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True


class _QuitTimeoutStub:
    def __init__(self):
        self.transport = _TransportSpy()

    def quit(self):
        raise TimeoutError("quit sem resposta")


def test_close_tolerates_quit_timeout_kills_process_and_restart_reopens(monkeypatch):
    engine = StockfishEngine.__new__(StockfishEngine)
    stub = _QuitTimeoutStub()
    engine._engine = stub
    open_calls: list[bool] = []
    monkeypatch.setattr(engine, "_open", lambda: open_calls.append(True))
    engine.restart()  # close() must not raise despite quit() raising TimeoutError
    assert stub.transport.killed is True
    assert open_calls == [True]


def test_find_stockfish_prefers_configured(tmp_path):
    exe = tmp_path / "stockfish.exe"
    exe.write_bytes(b"")
    assert find_stockfish(str(exe)) == str(exe)


def test_find_stockfish_respeita_a_variavel_de_ambiente(tmp_path, monkeypatch):
    from chess_trainer.core.analysis.engine import find_stockfish
    binario = tmp_path / "stockfish"
    binario.write_bytes(b"")
    monkeypatch.setenv("STOCKFISH_PATH", str(binario))
    assert find_stockfish("") == str(binario)
    monkeypatch.setenv("STOCKFISH_PATH", str(tmp_path / "nao-existe"))
    monkeypatch.setattr("shutil.which", lambda _n: None)
    assert find_stockfish("") is None or not find_stockfish("").endswith("nao-existe")


@pytest.mark.slow
def test_real_stockfish_finds_mate_in_one():
    path = find_stockfish(os.environ.get("STOCKFISH_PATH", ""))
    if not path:
        pytest.skip("Stockfish não encontrado")
    engine = StockfishEngine(path, threads=2, hash_mb=64)
    try:
        board = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        lines = engine.analyse(board, depth=10, multipv=2)
        assert lines[0].move == "a1a8"
        assert is_mate_for(lines[0].score)
        assert lines[0].pv[0] == "a1a8"
        assert len(lines) == 2
    finally:
        engine.close()


@pytest.mark.slow
def test_real_stockfish_finds_mate_in_one_with_time_cap():
    path = find_stockfish(os.environ.get("STOCKFISH_PATH", ""))
    if not path:
        pytest.skip("Stockfish não encontrado")
    engine = StockfishEngine(path, threads=2, hash_mb=64)
    try:
        board = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        lines = engine.analyse(board, depth=10, max_seconds=1.0)
        assert lines[0].move == "a1a8"
        assert is_mate_for(lines[0].score)
    finally:
        engine.close()


@pytest.mark.slow
def test_real_stockfish_interactive_analyzer_finds_mate_in_one():
    path = find_stockfish(os.environ.get("STOCKFISH_PATH", ""))
    if not path:
        pytest.skip("Stockfish não encontrado")
    az = InteractiveAnalyzer(lambda: StockfishEngine(path))
    try:
        r = az.analyse("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        assert r["lines"][0]["san"] == "Ra8#"
    finally:
        az.close()
