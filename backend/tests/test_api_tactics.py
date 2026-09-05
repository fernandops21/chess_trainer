from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.tactics.importer import write_csv_zst
from tests.fakes import FakeEngine, first_legal_default
from tests.test_tactics_importer import ROWS


@pytest.fixture
def client(tmp_path: Path):
    src = tmp_path / "puzzles.csv.zst"
    write_csv_zst(src, ROWS)
    app = create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)), tactics_source=src)
    with TestClient(app) as c:
        yield c


def run_import(client):
    # as linhas de teste têm poucas partidas/popularidade: afrouxa o filtro padrão (2000/90)
    assert client.put("/api/settings", json={"lichess_min_plays": 200, "lichess_min_popularity": 60}).status_code == 200
    assert client.post("/api/tactics/import").status_code == 202
    client.app.state.jobs.wait()
    job = client.get("/api/status").json()["job"]
    assert job["state"] == "idle", job


def test_next_404_before_import(client):
    r = client.get("/api/tactics/next")
    assert r.status_code == 404 and "não importado" in r.json()["detail"]
    assert client.get("/api/tactics/status").json()["imported"] is False


def test_import_then_train_flow(client):
    run_import(client)
    st = client.get("/api/tactics/status").json()
    assert st["imported"] and st["count"] == 2 and st["imported_at"] and st["source_rows"] == 5
    themes = client.get("/api/tactics/themes").json()
    assert {t["theme"] for t in themes} >= {"fork", "mateIn2"} and next(t for t in themes if t["theme"] == "fork")["label"] == "garfo"
    r = client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50})
    assert r.status_code == 200 and r.json()["tactics_rating"] == 1760
    t = client.get("/api/tactics/next").json()
    assert t["id"] == "00sHx" and t["kind"] == "tactic" and t["solution"]["moves"][0]["by"] == "solver"
    assert t["lichess_url"].endswith("/training/00sHx") and t["end_reason"] == "mate"
    a = client.post("/api/tactics/attempts", json={"puzzle_id": t["id"], "correct": True, "duration_ms": 5000}).json()
    assert a["rating_before"] == 1760 and a["delta"] == 16 and a["rating_after"] == 1776
    assert client.get("/api/settings").json()["tactics_rating"] == 1776
    # resolvido não volta; com exclude do outro, nada sobra
    r = client.get("/api/tactics/next", params={"exclude": "00sJ9"})
    assert r.status_code == 404
    stats = client.get("/api/stats/themes").json()
    assert stats[0]["theme"] == "mateIn2" and stats[0]["attempts"] == 1 and stats[0]["lichess"] == 1
    assert client.get("/api/tactics/status").json()["attempts_today"] == 1


def test_attempt_unknown_puzzle_404(client):
    run_import(client)
    assert client.post("/api/tactics/attempts", json={"puzzle_id": "nope", "correct": False}).status_code == 404


def test_import_busy_409(client):
    import threading
    gate = threading.Event()
    client.app.state.jobs.submit("import", lambda progress: gate.wait(5))
    try:
        assert client.post("/api/tactics/import").status_code == 409
    finally:
        gate.set()
        client.app.state.jobs.wait()


def test_next_404_when_no_tactic_matches_filters(client):
    run_import(client)
    r = client.get("/api/tactics/next", params={"themes": " skewer , "})
    assert r.status_code == 404 and r.json()["detail"] == "nenhuma tática disponível com esses filtros"


def test_attempt_unknown_session_404(client):
    run_import(client)
    r = client.post("/api/tactics/attempts", json={"puzzle_id": "00sHx", "correct": True, "session_id": "nada"})
    assert r.status_code == 404 and r.json()["detail"] == "sessão não encontrada"
