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


def _positions(app):
    """Posições da partida analisada, na ordem dos plies."""
    from sqlalchemy import select

    from chess_trainer.core.models import Position

    with app.state.session_factory() as db:
        rows = db.scalars(select(Position).order_by(Position.ply)).all()
        return [{"id": p.id, "game_id": p.game_id, "ply": p.ply, "fen": p.fen, "move_uci": p.move_uci} for p in rows]


def _make_avoid(app, pos: dict) -> str:
    """Cria um puzzle "evitar" ligado a essa posição (o gerador só cria evitar
    para erros do usuário; aqui interessa só a saída da API)."""
    from chess_trainer.core.models import Puzzle

    with app.state.session_factory() as db:
        puzzle = Puzzle(position_id=pos["id"], game_id=pos["game_id"], kind="avoid", fen_start=pos["fen"],
                        side_to_move="white", solution='{"moves": [], "explanation_pv": []}',
                        end_reason="material_gain", theme="tactic", category="rapid", solver_moves=1)
        db.add(puzzle)
        db.commit()
        return puzzle.id


def test_puzzle_out_last_move_for_own_punish_and_avoid(ready):
    app, client = ready
    positions = _positions(app)
    punish = client.get("/api/queue").json()["items"][0]
    # punir: o último lance é o próprio erro do adversário, a partir da posição anterior a ele
    assert punish["source"] == "own" and punish["kind"] == "punish" and punish["in_queue"] is True
    assert punish["last_move"] == "g8f6" and punish["fen_before"] == positions[5]["fen"]
    assert punish["study"] is None and punish["game"] is not None and punish["ply"] == 6

    # evitar: o último lance é o do adversário, um ply antes do erro do usuário
    avoid_id = _make_avoid(app, positions[4])
    avoid = client.get(f"/api/puzzles/{avoid_id}").json()
    assert avoid["kind"] == "avoid" and avoid["last_move"] == positions[3]["move_uci"]
    assert avoid["fen_before"] == positions[3]["fen"]

    # no ply 1 não há lance anterior: sem último lance
    first = client.get(f"/api/puzzles/{_make_avoid(app, positions[0])}").json()
    assert first["fen_before"] is None and first["last_move"] is None


def test_queue_toggle_removes_from_queue_and_dashboard(ready):
    _, client = ready
    puzzle = client.get("/api/queue").json()["items"][0]
    by_source = client.get("/api/dashboard").json()["by_source"]
    assert by_source["own"] == {"in_queue": 1, "due": 0}
    assert by_source["lichess"] == {"in_queue": 0, "due": 0} and by_source["study"]["in_queue"] == 0

    out = client.post(f"/api/puzzles/{puzzle['id']}/queue", json={"in_queue": False})
    assert out.status_code == 200 and out.json()["in_queue"] is False
    q = client.get("/api/queue").json()
    assert q["items"] == [] and q["new_available"] == 0
    assert client.get("/api/dashboard").json()["by_source"]["own"]["in_queue"] == 0
    # o puzzle e seu histórico continuam: a revisão de erros ainda o lista, fora da repetição
    mistakes = client.get("/api/mistakes", params={"by": "all"}).json()
    assert mistakes[0]["puzzles"][0]["in_queue"] is False

    back = client.post(f"/api/puzzles/{puzzle['id']}/queue", json={"in_queue": True})
    assert back.status_code == 200 and back.json()["in_queue"] is True
    assert len(client.get("/api/queue").json()["items"]) == 1
    assert client.get("/api/dashboard").json()["by_source"]["own"]["in_queue"] == 1
    assert client.post("/api/puzzles/nope/queue", json={"in_queue": True}).status_code == 404


def test_queue_filters_by_source(ready):
    _, client = ready
    assert client.get("/api/queue", params={"sources": "lichess"}).json()["items"] == []
    assert len(client.get("/api/queue", params={"sources": "own, lichess"}).json()["items"]) == 1
    assert client.get("/api/queue", params={"study_id": "nenhum"}).json()["items"] == []
