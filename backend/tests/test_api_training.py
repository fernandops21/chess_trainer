from datetime import datetime

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
    # a repetição espaçada não serve quem nunca foi feito: a primeira vez é em "Novos"
    vazia = client.get("/api/queue").json()
    assert vazia["mode"] == "review" and vazia["items"] == [] and vazia["due_count"] == 0
    assert vazia["new_available"] == 1

    q = client.get("/api/queue", params={"mode": "new"}).json()
    assert q["mode"] == "new" and q["due_count"] == 0 and q["new_available"] == 1 and len(q["items"]) == 1
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
    assert client.get("/api/queue", params={"mode": "new"}).json()["items"] == []

    ended = client.post(f"/api/sessions/{session['id']}/end").json()
    assert ended["reviews"] == 1 and ended["correct"] == 1 and ended["total_duration_ms"] == 4000
    assert ended["ended_at"] is not None

    dash = client.get("/api/dashboard").json()
    assert dash["due_today"] == 0 and dash["reviews_today"] == 1 and dash["streak_days"] == 1
    assert dash["games_total"] == 1 and dash["games_analyzed"] == 1 and dash["puzzles_total"] == 1
    assert dash["last_import_at"] is not None


def test_leech_and_unleech(ready):
    _, client = ready
    puzzle = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]
    for _ in range(2):
        r = client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "correct": False})
    assert r.json()["is_leech"] is True
    leeches = client.get("/api/leeches").json()
    assert [p["id"] for p in leeches] == [puzzle["id"]]
    assert client.get("/api/dashboard").json()["leeches"] == 1
    back = client.post(f"/api/puzzles/{puzzle['id']}/unleech").json()
    assert back["is_leech"] is False and back["srs"]["lapses"] == 0
    assert client.get("/api/queue").json()["due_count"] == 1


def test_queue_count_only_devolve_so_as_contagens(ready):
    """`count_only=1` monta a mesma fila, mas responde sem serializar os puzzles."""
    _, client = ready
    novos = client.get("/api/queue", params={"mode": "new"}).json()
    assert len(novos["items"]) == 1

    contagem = client.get("/api/queue", params={"mode": "new", "count_only": 1}).json()
    assert contagem["items"] == []
    assert {k: v for k, v in contagem.items() if k != "items"} == {k: v for k, v in novos.items() if k != "items"}

    # com um exercício realmente vencido, o `due_count` continua o mesmo
    puzzle = novos["items"][0]
    for _ in range(2):
        client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "correct": False})
    client.post(f"/api/puzzles/{puzzle['id']}/unleech")
    fila = client.get("/api/queue").json()
    assert fila["due_count"] == 1 and len(fila["items"]) == 1

    so_contagem = client.get("/api/queue", params={"count_only": 1}).json()
    assert so_contagem["items"] == [] and so_contagem["due_count"] == fila["due_count"]


def test_puzzle_out_carries_mistake_and_siblings(ready):
    _, client = ready
    puzzle = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]
    m = puzzle["mistake"]
    assert m["ply"] == 6 and m["move_played"] == "Nf6" and m["move_uci"] == "g8f6"
    assert m["mistake_level"] == "blunder" and m["mistake_by"] == "opponent"
    assert m["eval_before"] == 0 and m["eval_after"] < -90000
    assert puzzle["siblings"] == []


def test_punir_traz_a_resposta_que_voce_deu_na_partida(ready):
    """No "punir" o cartão do resultado mostra o que o usuário respondeu ao erro
    do adversário: a posição do ply seguinte, na mesma partida."""
    app, client = ready
    positions = _positions(app)
    seguinte = positions[6]
    assert seguinte["ply"] == 7
    puzzle = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]
    reply = puzzle["mistake"]["my_reply"]
    assert reply["ply"] == 7 and reply["move_uci"] == seguinte["move_uci"]
    assert reply["move_played"] and "eval_before" in reply and "eval_after" in reply


def test_punir_no_ultimo_lance_da_partida_nao_tem_resposta(ready):
    """Sem ply seguinte (o erro foi o último lance) `my_reply` é nulo."""
    from sqlalchemy import select

    from chess_trainer.core.models import Position

    app, client = ready
    puzzle_id = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]["id"]
    with app.state.session_factory() as db:
        db.delete(db.scalars(select(Position).where(Position.ply == 7)).one())
        db.commit()
    assert client.get(f"/api/puzzles/{puzzle_id}").json()["mistake"]["my_reply"] is None


def test_respostas_da_partida_em_lote_nao_misturam_as_partidas(ready):
    """`_my_replies` roda para a fila inteira: pede as posições por partida e
    peneira os pares `(partida, ply)` em Python — com três exercícios de duas
    partidas, cada um recebe a resposta do seu próprio ply seguinte, e o ply
    que existe só na outra partida não vaza."""
    from chess_trainer.api.routes.training import _my_replies
    from chess_trainer.core.models import Game, Position, Puzzle

    app, _ = ready
    with app.state.session_factory() as db:
        outra = Game(source_id="outra-partida", pgn="[Event \"?\"]", white="a", black="b", result="1-0",
                     time_control="600", category="rapid", played_at=datetime(2024, 1, 1), my_color="white")
        db.add(outra)
        db.flush()
        # a outra partida tem plies 4 e 5; a primeira, os plies 0..6 da fixture
        for ply in (4, 5):
            db.add(Position(game_id=outra.id, ply=ply, fen=f"fen-{ply}", move_played=f"L{ply}",
                            move_uci="a2a3", eval_before=10 * ply, eval_after=20 * ply))
        db.flush()

        def puzzle_em(game_id: str, ply: int) -> Puzzle:
            pos = db.query(Position).filter_by(game_id=game_id, ply=ply).one()
            pos.is_mistake, pos.mistake_by, pos.mistake_level = True, "opponent", "blunder"
            p = Puzzle(position_id=pos.id, game_id=game_id, kind="punish", fen_start=f"{game_id}-{ply}",
                       side_to_move="white", solution='{"moves": [], "explanation_pv": []}',
                       end_reason="material_gain", theme="tactic", category="rapid", solver_moves=1)
            db.add(p)
            return p

        primeira = db.query(Position).filter_by(ply=6).one().game_id
        # ply 4 nas duas partidas (o par tem de casar nos dois campos) e ply 5 só na outra
        a = puzzle_em(primeira, 4)
        b = puzzle_em(outra.id, 4)
        c = puzzle_em(outra.id, 5)
        db.commit()
        respostas = _my_replies(db, [a, b, c])

        assert set(respostas) == {a.id, b.id}          # o ply 6 da outra partida não existe
        assert respostas[a.id].ply == 5 and respostas[a.id].move_played != "L5"
        assert respostas[b.id].ply == 5 and respostas[b.id].move_played == "L5"


def test_evitar_nao_tem_resposta_da_partida(ready):
    """No "evitar" o erro é do próprio usuário: não há o que ele respondeu."""
    app, client = ready
    from chess_trainer.core.models import Position

    pos = _positions(app)[4]
    # a posição da fixture não é erro de ninguém: marca como erro do usuário, o caso do "evitar"
    with app.state.session_factory() as db:
        row = db.get(Position, pos["id"])
        row.is_mistake, row.mistake_by, row.mistake_level = True, "me", "mistake"
        db.commit()
    avoid_id = _make_puzzle(app, pos, "avoid")
    assert client.get(f"/api/puzzles/{avoid_id}").json()["mistake"]["my_reply"] is None


def test_review_unknown_puzzle_is_404(ready):
    _, client = ready
    assert client.post("/api/reviews", json={"puzzle_id": "nope", "correct": True}).status_code == 404


def test_review_unknown_session_is_404(ready):
    _, client = ready
    puzzle = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]
    r = client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "session_id": "nope", "correct": True})
    assert r.status_code == 404 and "sessão" in r.json()["detail"]


def _positions(app):
    """Posições da partida analisada, na ordem dos plies."""
    from sqlalchemy import select

    from chess_trainer.core.models import Position

    with app.state.session_factory() as db:
        rows = db.scalars(select(Position).order_by(Position.ply)).all()
        return [{"id": p.id, "game_id": p.game_id, "ply": p.ply, "fen": p.fen, "move_uci": p.move_uci} for p in rows]


def _make_puzzle(app, pos: dict, kind: str = "avoid") -> str:
    """Cria um puzzle ligado a essa posição (o gerador só cria evitar para erros
    do usuário; aqui interessa só a saída da API)."""
    from chess_trainer.core.models import Puzzle

    with app.state.session_factory() as db:
        puzzle = Puzzle(position_id=pos["id"], game_id=pos["game_id"], kind=kind, fen_start=pos["fen"],
                        side_to_move="white", solution='{"moves": [], "explanation_pv": []}',
                        end_reason="material_gain", theme="tactic", category="rapid", solver_moves=1)
        db.add(puzzle)
        db.commit()
        return puzzle.id


def test_puzzle_out_last_move_for_own_punish_and_avoid(ready):
    app, client = ready
    positions = _positions(app)
    punish = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]
    # punir: o último lance é o próprio erro do adversário, a partir da posição anterior a ele
    assert punish["source"] == "own" and punish["kind"] == "punish" and punish["in_queue"] is True
    assert punish["last_move"] == "g8f6" and punish["fen_before"] == positions[5]["fen"]
    assert punish["study"] is None and punish["game"] is not None and punish["ply"] == 6

    # evitar: o último lance é o do adversário, um ply antes do erro do usuário
    avoid_id = _make_puzzle(app, positions[4], "avoid")
    avoid = client.get(f"/api/puzzles/{avoid_id}").json()
    assert avoid["kind"] == "avoid" and avoid["last_move"] == positions[3]["move_uci"]
    assert avoid["fen_before"] == positions[3]["fen"]

    # no ply 1 não há lance anterior: sem último lance
    first = client.get(f"/api/puzzles/{_make_puzzle(app, positions[0], 'avoid')}").json()
    assert first["fen_before"] is None and first["last_move"] is None


def test_queue_toggle_removes_from_queue_and_dashboard(ready):
    _, client = ready
    puzzle = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]
    by_source = client.get("/api/dashboard").json()["by_source"]
    assert by_source["own"] == {"in_queue": 1, "due": 0}
    assert by_source["lichess"] == {"in_queue": 0, "due": 0} and by_source["study"]["in_queue"] == 0

    out = client.post(f"/api/puzzles/{puzzle['id']}/queue", json={"in_queue": False})
    assert out.status_code == 200 and out.json()["in_queue"] is False
    q = client.get("/api/queue", params={"mode": "new"}).json()
    assert q["items"] == [] and q["new_available"] == 0
    assert client.get("/api/dashboard").json()["by_source"]["own"]["in_queue"] == 0
    # o puzzle e seu histórico continuam: a revisão de erros ainda o lista, fora da repetição
    mistakes = client.get("/api/mistakes", params={"by": "all"}).json()
    assert mistakes[0]["puzzles"][0]["in_queue"] is False

    back = client.post(f"/api/puzzles/{puzzle['id']}/queue", json={"in_queue": True})
    assert back.status_code == 200 and back.json()["in_queue"] is True
    assert len(client.get("/api/queue", params={"mode": "new"}).json()["items"]) == 1
    assert client.get("/api/dashboard").json()["by_source"]["own"]["in_queue"] == 1
    assert client.post("/api/puzzles/nope/queue", json={"in_queue": True}).status_code == 404


def test_dashboard_counts_due_by_source(ready):
    """A coluna `due` do painel por fonte conta os vencidos. Sem um exercício com
    `srs_due_at` no passado ela ficaria sempre em zero e o teste não diria nada."""
    from chess_trainer.core.models import Puzzle

    app, client = ready
    puzzle_id = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]["id"]
    db = app.state.session_factory()
    try:
        db.get(Puzzle, puzzle_id).srs_due_at = datetime(2020, 1, 1)
        db.commit()
    finally:
        db.close()

    dash = client.get("/api/dashboard").json()
    assert dash["by_source"]["own"] == {"in_queue": 1, "due": 1}
    assert dash["by_source"]["lichess"] == {"in_queue": 0, "due": 0}
    assert dash["due_today"] == 1


def test_queue_filters_by_source(ready):
    _, client = ready
    assert client.get("/api/queue", params={"mode": "new", "sources": "lichess"}).json()["items"] == []
    assert len(client.get("/api/queue", params={"mode": "new", "sources": "own, lichess"}).json()["items"]) == 1
    assert client.get("/api/queue", params={"mode": "new", "study_id": "nenhum"}).json()["items"] == []


def test_modo_invalido_e_estudo_sem_id_sao_recusados(ready):
    _, client = ready
    assert client.get("/api/queue", params={"mode": "qualquer"}).status_code == 422
    r = client.get("/api/queue", params={"mode": "study"})
    assert r.status_code == 400 and "estudo" in r.json()["detail"]


def test_painel_conta_vencidos_e_novos_dos_meus_erros(ready):
    """O painel separa o que está vencido (repetição) do que nunca foi feito
    (novos), para os dois botões da tela inicial."""
    app, client = ready
    dash = client.get("/api/dashboard").json()
    assert dash["due_today"] == 0 and dash["new_available"] == 1 and dash["new_remaining_today"] == 10

    puzzle_id = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]["id"]
    assert client.post("/api/reviews", json={"puzzle_id": puzzle_id, "correct": False}).status_code == 201
    dash = client.get("/api/dashboard").json()
    # a revisão de hoje já não conta como novo e desconta do limite diário
    assert dash["new_available"] == 0 and dash["new_remaining_today"] == 9
