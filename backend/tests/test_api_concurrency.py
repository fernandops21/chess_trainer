"""A API precisa continuar gravando enquanto um job pensa com a engine (SQLite não travado)."""
import threading
import time

import chess
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from tests.fakes import FakeEngine, first_legal_default
from tests.test_api_system import chesscom_factory

PUZZLE_SLEEP = 1.5


def _before_mate() -> chess.Board:
    b = chess.Board()
    for u in ("e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6"):
        b.push_uci(u)
    return b


class SlowPuzzleEngine(FakeEngine):
    """Demora só nas chamadas de geração de puzzle (multipv=3), como o Stockfish real em profundidade."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.thinking = threading.Event()

    def analyse(
        self, board: chess.Board, depth: int, multipv: int = 1, max_seconds: float | None = None,
    ) -> list[LineEval]:
        if multipv == 3:
            self.thinking.set()
            time.sleep(PUZZLE_SLEEP)
        return super().analyse(board, depth, multipv, max_seconds)


def test_settings_write_is_not_blocked_by_running_analysis(tmp_path):
    engine = SlowPuzzleEngine({_before_mate().epd(): [LineEval("h5f7", MATE_SCORE - 1, ("h5f7",))]},
                              first_legal_default(0))
    app = create_app(db_path=str(tmp_path / "t.db"), engine_factory=lambda s: engine,
                     chesscom_factory=chesscom_factory)
    client = TestClient(app)
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import")
    app.state.jobs.wait(timeout=10)

    assert client.post("/api/analyze").status_code == 202
    assert engine.thinking.wait(timeout=10), "a geração de puzzles não chegou a começar"

    started = time.monotonic()
    r = client.put("/api/settings", json={"new_per_day": 7})
    elapsed = time.monotonic() - started
    assert r.status_code == 200 and r.json()["new_per_day"] == 7
    assert elapsed < 1.0, f"a escrita esperou {elapsed:.2f}s pelo lock do job de análise"

    app.state.jobs.wait(timeout=15)
    snap = app.state.jobs.snapshot()
    assert snap["state"] == "idle" and snap["error"] is None
    status = client.get("/api/status").json()
    assert status["games_pending"] == 0 and status["job"]["state"] == "idle"
    assert client.get("/api/queue").json()["new_available"] == 1  # o puzzle foi gravado
