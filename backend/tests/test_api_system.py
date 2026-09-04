import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.importers.chesscom import ChessComClient
from tests.fakes import FakeEngine, first_legal_default

FIXTURES = Path(__file__).parent / "fixtures"


def chesscom_factory(settings):
    def handler(request: httpx.Request):
        if request.url.path.endswith("/games/archives"):
            return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_archives.json").read_text()))
        if request.url.path.endswith("/2026/08"):
            return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_month.json").read_text()))
        return httpx.Response(200, json={"games": []})
    return ChessComClient("t", http=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def app():
    return create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)),
                      chesscom_factory=chesscom_factory)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_status_and_settings_roundtrip(client):
    status = client.get("/api/status").json()
    assert status["engine"]["available"] is True
    assert status["job"]["state"] == "idle" and status["games_total"] == 0

    assert client.get("/api/settings").json()["new_per_day"] == 10
    r = client.put("/api/settings", json={"chesscom_username": " TheRealZibs ", "new_per_day": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["chesscom_username"] == "therealzibs" and body["new_per_day"] == 5
    assert body["analysis_depth"] == 18  # não enviado, mantido


def test_import_requires_username(client):
    assert client.post("/api/import").status_code == 400


def test_import_job_runs_and_reports(client, app):
    client.put("/api/settings", json={"chesscom_username": "therealzibs"})
    r = client.post("/api/import")
    assert r.status_code == 202 and r.json()["job"] == "import"
    app.state.jobs.wait()
    status = client.get("/api/status").json()
    assert status["job"]["state"] == "idle" and status["job"]["job"] == "import"
    assert status["games_total"] == 1 and status["games_pending"] == 1
    assert status["last_import_at"] is not None


def test_analyze_job_and_regenerate(client, app):
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import"); app.state.jobs.wait()
    r = client.post("/api/analyze", params={"limit": 5})
    assert r.status_code == 202
    app.state.jobs.wait()
    status = client.get("/api/status").json()
    assert status["job"]["state"] == "idle" and status["games_pending"] == 0
    r = client.post("/api/puzzles/regenerate")
    assert r.status_code == 202
    app.state.jobs.wait()
    assert client.get("/api/status").json()["job"]["state"] == "idle"


def test_analyze_without_engine_is_503():
    app = create_app(db_path=":memory:", engine_factory=lambda s: None, chesscom_factory=chesscom_factory)
    client = TestClient(app)
    assert client.get("/api/status").json()["engine"]["available"] is False
    assert client.post("/api/analyze").status_code == 503


def test_second_job_while_busy_is_409(client, app):
    import threading
    release = threading.Event()
    started = threading.Event()

    def blocking(progress):
        started.set()
        release.wait(timeout=10)

    assert app.state.jobs.submit("analyze", blocking) is True
    started.wait(timeout=5)
    client.put("/api/settings", json={"chesscom_username": "therealzibs"})
    assert client.post("/api/import").status_code == 409
    assert client.post("/api/analyze").status_code == 409
    release.set()
    app.state.jobs.wait()
    assert client.get("/api/status").json()["job"]["state"] == "idle"


def test_job_error_is_reported(app):
    def boom(progress):
        raise RuntimeError("falhou feio")
    assert app.state.jobs.submit("import", boom) is True
    app.state.jobs.wait()
    snap = app.state.jobs.snapshot()
    assert snap["state"] == "error" and "falhou feio" in snap["error"]
    assert app.state.jobs.submit("import", lambda p: None) is True  # volta a aceitar
