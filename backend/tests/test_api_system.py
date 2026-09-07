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

    initial = client.get("/api/settings").json()
    assert initial["new_per_day"] == 10
    assert initial["analysis_seconds"] == 15
    assert initial["puzzle_search_seconds"] == 20 and initial["puzzle_reply_seconds"] == 10
    assert initial["classify_moves"] is True
    r = client.put("/api/settings", json={
        "chesscom_username": " TheRealZibs ", "new_per_day": 5,
        "analysis_seconds": 30, "puzzle_search_seconds": 25, "puzzle_reply_seconds": 8,
        "classify_moves": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["chesscom_username"] == "therealzibs" and body["new_per_day"] == 5
    assert body["analysis_depth"] == 18  # não enviado, mantido
    assert body["analysis_seconds"] == 30
    assert body["puzzle_search_seconds"] == 25 and body["puzzle_reply_seconds"] == 8
    assert body["classify_moves"] is False
    assert client.get("/api/settings").json()["classify_moves"] is False


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


def test_regenerate_kind_avoid_route(client, app):
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import"); app.state.jobs.wait()
    r = client.post("/api/puzzles/regenerate", params={"kind": "avoid"})
    assert r.status_code == 202 and r.json()["job"] == "regenerate_avoid"
    app.state.jobs.wait()
    assert app.state.jobs.snapshot()["state"] == "idle"
    assert client.post("/api/puzzles/regenerate", params={"kind": "xyz"}).status_code == 422


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


def test_cancel_when_idle_is_409(client):
    assert client.post("/api/jobs/cancel").status_code == 409


def test_cancel_stops_running_job(client, app):
    import threading
    import time
    started = threading.Event()

    def looping(progress):
        started.set()
        for _ in range(500):  # ~10 s no pior caso; o cancel encerra bem antes
            if app.state.jobs.should_stop():
                return
            time.sleep(0.02)
        raise AssertionError("job não foi cancelado")

    assert app.state.jobs.submit("analyze", looping) is True
    started.wait(timeout=5)
    r = client.post("/api/jobs/cancel")
    assert r.status_code == 202 and r.json() == {"cancelled": True}
    app.state.jobs.wait(timeout=10)
    job = client.get("/api/status").json()["job"]
    assert job["state"] == "idle" and "cancelado" in job["message"]
    assert client.post("/api/jobs/cancel").status_code == 409  # já terminou


def test_cancel_requested_flag_reported_and_reset(client, app):
    import threading
    started = threading.Event()
    release = threading.Event()

    def blocking(progress):
        started.set()
        release.wait(timeout=10)

    assert app.state.jobs.submit("analyze", blocking) is True
    started.wait(timeout=5)
    r = client.post("/api/jobs/cancel")
    assert r.status_code == 202
    status = client.get("/api/status").json()
    assert status["job"]["cancel_requested"] is True
    release.set()
    app.state.jobs.wait(timeout=10)

    assert app.state.jobs.submit("import", lambda p: None) is True
    app.state.jobs.wait(timeout=10)
    status = client.get("/api/status").json()
    assert status["job"]["cancel_requested"] is False


def test_analyze_single_game(client, app):
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import"); app.state.jobs.wait()
    game_id = client.get("/api/games").json()[0]["id"]
    assert client.post("/api/analyze", params={"game_id": "nope"}).status_code == 404
    r = client.post("/api/analyze", params={"game_id": game_id})
    assert r.status_code == 202
    app.state.jobs.wait()
    assert client.get(f"/api/games/{game_id}").json()["analyzed_at"] is not None
    assert client.post("/api/analyze", params={"game_id": game_id}).status_code == 409


def test_status_has_local_url(client):
    url = client.get("/api/status").json()["local_url"]
    assert url.startswith("http://") and url.endswith(":8000")


def test_local_url_respects_loopback_host(client, monkeypatch):
    # servindo só em loopback, a URL de LAN não abriria em lugar nenhum
    monkeypatch.setenv("CHESS_TRAINER_HOST", "127.0.0.1")
    monkeypatch.setenv("CHESS_TRAINER_PORT", "8123")
    assert client.get("/api/status").json()["local_url"] == "http://127.0.0.1:8123"
    monkeypatch.setenv("CHESS_TRAINER_HOST", "localhost")
    assert client.get("/api/status").json()["local_url"] == "http://127.0.0.1:8123"


def test_local_url_is_lan_when_host_is_wildcard(client, monkeypatch):
    monkeypatch.setenv("CHESS_TRAINER_HOST", "0.0.0.0")
    monkeypatch.setattr("chess_trainer.api.routes.system.local_ip", lambda: "192.168.0.7")
    assert client.get("/api/status").json()["local_url"] == "http://192.168.0.7:8000"


def test_token_do_lichess_nunca_volta_nas_respostas(client):
    inicial = client.get("/api/settings").json()
    assert inicial["lichess_token_set"] is False and "lichess_token" not in inicial

    body = client.put("/api/settings", json={"lichess_token": "  lip_segredo  "}).json()
    assert body["lichess_token_set"] is True and "lichess_token" not in body
    assert "lip_segredo" not in client.get("/api/settings").text

    # outra alteração sem o campo mantém o token guardado
    body = client.put("/api/settings", json={"new_per_day": 7}).json()
    assert body["new_per_day"] == 7 and body["lichess_token_set"] is True

    # string vazia apaga
    assert client.put("/api/settings", json={"lichess_token": ""}).json()["lichess_token_set"] is False
    assert client.get("/api/settings").json()["lichess_token_set"] is False
