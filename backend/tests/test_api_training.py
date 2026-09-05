import chess
import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from tests.fakes import FakeEngine, first_legal_default
from tests.test_api_system import chesscom_factory


def _before_mate() -> chess.Board:
    b = chess.Board()
    for u in ("e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6"):
        b.push_uci(u)
    return b


def engine_factory(settings):
    return FakeEngine({_before_mate().epd(): [LineEval("h5f7", MATE_SCORE - 1, ("h5f7",))]},
                      first_legal_default(0))


@pytest.fixture
def ready(tmp_path):
    """App com uma partida importada e analisada (1 puzzle mate_in_1, erro do adversário)."""
    app = create_app(db_path=":memory:", engine_factory=engine_factory, chesscom_factory=chesscom_factory)
    client = TestClient(app)
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4, "leech_lapses": 2})
    client.post("/api/import"); app.state.jobs.wait()
    client.post("/api/analyze"); app.state.jobs.wait()
    assert app.state.jobs.snapshot()["state"] == "idle"
    return app, client


def test_games_list_and_detail(ready):
    _, client = ready
    games = client.get("/api/games").json()
    assert len(games) == 1 and games[0]["category"] == "rapid" and games[0]["my_mistakes"] == 0
    assert client.get("/api/games", params={"category": "blitz"}).json() == []
    assert client.get("/api/games", params={"analyzed": "false"}).json() == []
    detail = client.get(f"/api/games/{games[0]['id']}").json()
    assert len(detail["positions"]) == 7 and detail["pgn"].startswith("[Event")
    ply6 = detail["positions"][5]
    assert ply6["is_mistake"] and ply6["mistake_level"] == "blunder" and len(ply6["puzzle_ids"]) == 1
    assert client.get("/api/games/nope").status_code == 404


def test_mistakes_listing(ready):
    _, client = ready
    assert client.get("/api/mistakes").json() == []                    # padrão: só os meus
    all_m = client.get("/api/mistakes", params={"by": "all"}).json()
    assert len(all_m) == 1 and all_m[0]["ply"] == 6 and all_m[0]["puzzles"][0]["theme"] == "mate_in_1"
    assert client.get("/api/mistakes", params={"by": "opponent", "level": "mistake"}).json() == []
    assert len(client.get("/api/mistakes", params={"by": "all", "theme": "mate_in_1"}).json()) == 1


def test_queue_review_and_dashboard_flow(ready):
    _, client = ready
    q = client.get("/api/queue").json()
    assert q["due_count"] == 0 and q["new_available"] == 1 and len(q["items"]) == 1
    puzzle = q["items"][0]
    assert puzzle["theme"] == "mate_in_1" and puzzle["solution"]["moves"][0]["uci"] == "h5f7"
    assert puzzle["srs"]["due_at"] is None and puzzle["game"]["white"] == "therealzibs"
    assert client.get(f"/api/puzzles/{puzzle['id']}").json()["id"] == puzzle["id"]

    session = client.post("/api/sessions", json={"planned_minutes": 25, "filters": {"kind": "punish"}}).json()
    r = client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "session_id": session["id"],
                                          "correct": True, "used_hint": False, "duration_ms": 4000})
    assert r.status_code == 201
    body = r.json()
    assert body["result"] == "correct" and body["interval_days"] == 1 and body["is_leech"] is False

    q2 = client.get("/api/queue").json()
    assert q2["due_count"] == 0 and q2["items"] == [] and q2["new_available"] == 0

    ended = client.post(f"/api/sessions/{session['id']}/end").json()
    assert ended["reviews"] == 1 and ended["correct"] == 1 and ended["total_duration_ms"] == 4000
    assert ended["ended_at"] is not None

    dash = client.get("/api/dashboard").json()
    assert dash["due_today"] == 0 and dash["reviews_today"] == 1 and dash["streak_days"] == 1
    assert dash["games_total"] == 1 and dash["games_analyzed"] == 1 and dash["puzzles_total"] == 1
    assert dash["last_import_at"] is not None


def test_leech_and_unleech(ready):
    _, client = ready
    puzzle = client.get("/api/queue").json()["items"][0]
    for _ in range(2):
        r = client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "correct": False})
    assert r.json()["is_leech"] is True
    leeches = client.get("/api/leeches").json()
    assert [p["id"] for p in leeches] == [puzzle["id"]]
    assert client.get("/api/dashboard").json()["leeches"] == 1
    back = client.post(f"/api/puzzles/{puzzle['id']}/unleech").json()
    assert back["is_leech"] is False and back["srs"]["lapses"] == 0
    assert client.get("/api/queue").json()["due_count"] == 1


def test_puzzle_out_carries_mistake_and_siblings(ready):
    _, client = ready
    puzzle = client.get("/api/queue").json()["items"][0]
    m = puzzle["mistake"]
    assert m["ply"] == 6 and m["move_played"] == "Nf6" and m["move_uci"] == "g8f6"
    assert m["mistake_level"] == "blunder" and m["mistake_by"] == "opponent"
    assert m["eval_before"] == 0 and m["eval_after"] < -90000
    assert puzzle["siblings"] == []


def test_review_unknown_puzzle_is_404(ready):
    _, client = ready
    assert client.post("/api/reviews", json={"puzzle_id": "nope", "correct": True}).status_code == 404


def test_review_unknown_session_is_404(ready):
    _, client = ready
    puzzle = client.get("/api/queue").json()["items"][0]
    r = client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "session_id": "nope", "correct": True})
    assert r.status_code == 404 and "sessão" in r.json()["detail"]
