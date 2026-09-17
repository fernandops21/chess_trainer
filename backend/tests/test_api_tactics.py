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
    # count e temas vêm do cache gravado no fim da importação, não de um count(*)
    assert st["imported"] and st["count"] == 2 and st["imported_at"] and st["source_rows"] == 5
    themes = client.get("/api/tactics/themes").json()
    assert {t["theme"] for t in themes} >= {"fork", "mateIn2"} and next(t for t in themes if t["theme"] == "fork")["label"] == "garfo"
    # fase/duração/avaliação são metadados do Lichess, não servem de filtro de treino
    assert {t["theme"] for t in themes}.isdisjoint({"short", "middlegame", "veryLong", "advantage"})
    r = client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50})
    assert r.status_code == 200 and r.json()["tactics_rating"] == 1760
    t = client.get("/api/tactics/next").json()
    assert t["id"] == "00sHx" and t["kind"] == "tactic" and t["solution"]["moves"][0]["by"] == "solver"
    assert t["lichess_url"].endswith("/training/00sHx") and t["end_reason"] == "mate"
    # a interface abre na posição de antes do lance do adversário e anima esse lance
    assert t["fen_before"] == ROWS[0]["FEN"] and t["last_move"] == "e8d7"
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


# uma linha corrompida (lance ilegal) e uma boa no mesmo ponto de rating: o sorteio
# cai em qualquer uma das duas, e a rota precisa devolver sempre a boa
CORRUPT_ROWS = [
    {"PuzzleId": "bad01", "FEN": "r3r1k1/p4ppp/2p2n2/1p6/3P1qb1/2NQR3/PPB2PP1/R1B3K1 w - - 5 18", "Moves": "e8e1 a2e6",
     "Rating": "1500", "RatingDeviation": "80", "Popularity": "90", "NbPlays": "900", "Themes": "fork",
     "GameUrl": "", "OpeningTags": ""},
    {"PuzzleId": "good1", "FEN": "q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17", "Moves": "e8d7 a2e6 d7d8 f7f8",
     "Rating": "1500", "RatingDeviation": "80", "Popularity": "90", "NbPlays": "900", "Themes": "mate mateIn2",
     "GameUrl": "", "OpeningTags": ""},
]


@pytest.fixture
def corrupt_client(tmp_path: Path):
    src = tmp_path / "corrupt.csv.zst"
    write_csv_zst(src, CORRUPT_ROWS)
    app = create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)), tactics_source=src)
    with TestClient(app) as c:
        yield c


def test_next_skips_corrupt_row_and_sorts_again(corrupt_client):
    run_import(corrupt_client)
    assert corrupt_client.put("/api/settings", json={"tactics_rating": 1500, "tactics_window": 50}).status_code == 200
    for _ in range(10):
        r = corrupt_client.get("/api/tactics/next")
        assert r.status_code == 200, r.json()
        assert r.json()["id"] == "good1"


def test_settings_rejects_window_below_minimum(client):
    assert client.put("/api/settings", json={"tactics_window": -50}).status_code == 422
    assert client.put("/api/settings", json={"tactics_rating": 90}).status_code == 422
    assert client.put("/api/settings", json={"lichess_min_plays": -1}).status_code == 422
    assert client.put("/api/settings", json={"lichess_min_popularity": 500}).status_code == 422


def test_themes_empty_while_importing_without_cache(client):
    # sem cache e com a importação rodando, a rota não pode disparar o GROUP BY
    # numa tabela que ainda está crescendo
    import threading
    gate = threading.Event()
    client.app.state.jobs.submit("import_lichess", lambda progress: gate.wait(5))
    try:
        assert client.get("/api/tactics/themes").json() == []
    finally:
        gate.set()
        client.app.state.jobs.wait()


FEN_00sHx = "q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17"


def test_save_tactic_creates_puzzle_and_is_idempotent(client):
    run_import(client)
    r = client.post("/api/tactics/00sHx/save")
    assert r.status_code == 201, r.json()
    p = r.json()
    assert p["source"] == "lichess" and p["in_queue"] is True and p["category"] == "lichess"
    assert p["kind"] == "punish" and p["theme"] == "mateIn2" and p["end_reason"] == "mate"
    # a tática começa na posição anterior ao lance do adversário, que é animado
    assert p["fen_before"] == FEN_00sHx and p["last_move"] == "e8d7"
    assert p["game"] is None and p["mistake"] is None and p["ply"] is None
    assert p["study"] is None and p["siblings"] == [] and p["solution"]["moves"][0]["by"] == "solver"

    again = client.post("/api/tactics/00sHx/save")
    assert again.status_code == 200 and again.json()["id"] == p["id"]
    assert client.post("/api/tactics/nada/save").status_code == 404


def test_save_tactic_gets_a_puzzle_signature(client):
    """Achado 2 da revisão: `post_save_tactic` criava o exercício sem assinar o golpe (spec
    §4.1, calculada quando o exercício é criado) — sem ela a rotulagem nunca via a tática
    guardada como âncora própria nem como irmão de bloco."""
    from sqlalchemy import select

    from chess_trainer.core.models import PuzzleSignature

    run_import(client)
    p = client.post("/api/tactics/00sHx/save").json()
    db = client.app.state.session_factory()
    try:
        assert db.scalar(select(PuzzleSignature).where(PuzzleSignature.puzzle_id == p["id"])) is not None
    finally:
        db.close()


def test_saved_tactic_enters_the_queue_and_accepts_reviews(client):
    run_import(client)
    p = client.post("/api/tactics/00sHx/save").json()
    assert client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50}).status_code == 200
    t = client.get("/api/tactics/next").json()
    assert t["id"] == "00sHx" and t["saved"] is True

    # guardada sem resultado, a tática só entra na repetição depois da primeira revisão
    q = client.get("/api/queue", params={"sources": "lichess"}).json()
    assert q["items"] == []
    r = client.post("/api/reviews", json={"puzzle_id": p["id"], "correct": True, "duration_ms": 3000})
    assert r.status_code == 201 and r.json()["interval_days"] == 1
    dash = client.get("/api/dashboard").json()
    assert dash["by_source"]["lichess"] == {"in_queue": 1, "due": 0} and dash["puzzles_total"] == 1

    # tirar da repetição: some da fila e deixa de aparecer como guardada
    assert client.post(f"/api/puzzles/{p['id']}/queue", json={"in_queue": False}).status_code == 200
    assert client.get("/api/queue", params={"sources": "lichess"}).json()["items"] == []
    assert client.get("/api/tactics/next").json()["saved"] is False
    # guardar de novo devolve o mesmo puzzle, de volta à fila
    again = client.post("/api/tactics/00sHx/save")
    assert again.status_code == 200 and again.json()["id"] == p["id"] and again.json()["in_queue"] is True


def test_guardar_a_tatica_com_o_resultado_ja_a_agenda(client):
    """Resolver a tática é a primeira vez dela: guardar com o resultado grava a
    revisão, e o exercício já sai agendado (sem passar por "Novos")."""
    run_import(client)
    r = client.post("/api/tactics/00sHx/save", json={"correct": True, "used_hint": False, "duration_ms": 4200})
    assert r.status_code == 201, r.json()
    p = r.json()
    assert p["srs"]["due_at"] is not None and p["srs"]["interval_days"] == 1
    assert p["srs"]["last_reviewed_at"] is not None

    revisoes = _reviews(client, p["id"])
    assert [(rev["result"], rev["duration_ms"]) for rev in revisoes] == [("correct", 4200)]

    # guardar de novo não inventa uma segunda revisão
    again = client.post("/api/tactics/00sHx/save", json={"correct": False})
    assert again.status_code == 200 and again.json()["id"] == p["id"]
    assert len(_reviews(client, p["id"])) == 1


def test_guardar_tatica_errada_pela_primeira_vez_conta_como_lapso(client):
    run_import(client)
    r = client.post("/api/tactics/00sHx/save", json={"correct": False})
    assert r.status_code == 201
    p = r.json()
    assert p["srs"]["interval_days"] == 1 and p["srs"]["lapses"] == 1


def test_guardar_tatica_com_dica_conta_como_erro_mesmo_se_correta(client):
    """Usar a dica desconta o mérito do acerto: no agendamento é tratado como erro."""
    run_import(client)
    r = client.post("/api/tactics/00sHx/save", json={"correct": True, "used_hint": True})
    assert r.status_code == 201
    p = r.json()
    assert p["srs"]["interval_days"] == 1 and p["srs"]["lapses"] == 1


def test_guardar_tatica_com_sessao_inexistente_nao_cria_puzzle(client):
    from sqlalchemy import select

    from chess_trainer.core.models import Puzzle

    run_import(client)
    r = client.post("/api/tactics/00sHx/save", json={"correct": True, "session_id": "nada"})
    assert r.status_code == 404
    db = client.app.state.session_factory()
    try:
        assert db.scalar(select(Puzzle)) is None
    finally:
        db.close()


def test_guardar_com_erro_agenda_como_erro_e_aceita_a_sessao(client):
    run_import(client)
    sessao = client.post("/api/sessions", json={"planned_minutes": 10}).json()
    r = client.post("/api/tactics/00sHx/save",
                    json={"correct": False, "used_hint": True, "duration_ms": 900, "session_id": sessao["id"]})
    assert r.status_code == 201
    assert r.json()["srs"]["due_at"] is not None
    revisoes = _reviews(client, r.json()["id"])
    assert [(rev["result"], rev["used_hint"], rev["session_id"]) for rev in revisoes] == [("wrong", True, sessao["id"])]
    assert client.post(f"/api/sessions/{sessao['id']}/end").json()["reviews"] == 1

    # sessão inexistente não passa
    assert client.post("/api/tactics/00sJ9/save",
                       json={"correct": True, "session_id": "nada"}).status_code == 404


def _reviews(client, puzzle_id: str) -> list[dict]:
    from sqlalchemy import select

    from chess_trainer.core.models import Review

    db = client.app.state.session_factory()
    try:
        rows = db.scalars(select(Review).where(Review.puzzle_id == puzzle_id)).all()
        return [{"result": r.result, "used_hint": r.used_hint, "duration_ms": r.duration_ms,
                 "session_id": r.session_id} for r in rows]
    finally:
        db.close()


# Duas táticas que transpõem para a mesma posição depois do lance do adversário
# (torre de d8 ou de a4 para d4): o exercício guardado é um só, pela única
# (fen_start, kind, source).
GEMEA_A = {"id": "gemA", "fen": "3r2k1/8/8/8/8/8/7P/Q5K1 b - - 0 1", "moves": "d8d4 a1d4"}
GEMEA_B = {"id": "gemB", "fen": "6k1/8/8/8/r7/8/7P/Q5K1 b - - 0 1", "moves": "a4d4 a1d4"}


def _add_gemeas(client):
    from chess_trainer.core.models import LichessPuzzle
    db = client.app.state.session_factory()
    try:
        for row in (GEMEA_A, GEMEA_B):
            db.add(LichessPuzzle(id=row["id"], fen=row["fen"], moves=row["moves"], rating=1500,
                                 rating_deviation=80, popularity=95, nb_plays=900, themes="fork"))
        db.commit()
    finally:
        db.close()


def test_twin_tactic_reports_saved_after_the_other_was_saved(client):
    """Guardar uma tática guarda a gêmea junto (mesma posição inicial): a tela
    de táticas precisa mostrar a segunda como já guardada, e não oferecer de novo."""
    run_import(client)
    _add_gemeas(client)
    assert client.put("/api/settings", json={"tactics_rating": 1500, "tactics_window": 50}).status_code == 200

    p = client.post("/api/tactics/gemA/save")
    assert p.status_code == 201

    # a segunda gêmea cai no mesmo exercício: a rota de salvar devolve o mesmo id...
    outra = client.post("/api/tactics/gemB/save")
    assert outra.status_code == 200 and outra.json()["id"] == p.json()["id"]

    # ...e a tela de treino já a mostra como guardada
    t = client.get("/api/tactics/next", params={"exclude": "00sHx,00sJ9,gemA"}).json()
    assert t["id"] == "gemB" and t["saved"] is True


def test_salvar_de_novo_com_sibling_of_completa_o_dado_que_faltava(client):
    """Achado 8 (deferido do achado 7): guardar sem `sibling_of` e depois de novo com um
    válido completa o campo (`_back_to_queue`, ramo do dado que faltava), sem sobrescrever
    uma origem já gravada."""
    run_import(client)
    assert client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50}).status_code == 200
    origem = client.get("/api/tactics/next").json()["id"]
    p_origem = client.post(f"/api/tactics/{origem}/save").json()
    outro = client.get(f"/api/tactics/next?exclude={origem}").json()["id"]

    sem_vinculo = client.post(f"/api/tactics/{outro}/save").json()
    assert sem_vinculo["sibling_of"] is None

    completo = client.post(f"/api/tactics/{outro}/save", json={"sibling_of": p_origem["id"]})
    assert completo.status_code == 200 and completo.json()["sibling_of"] == p_origem["id"]


def test_salvar_tatica_com_sibling_of(client):
    run_import(client)
    # janela larga: as duas táticas do fixture (1760 e 2671) precisam caber para o teste pegar as duas
    assert client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50}).status_code == 200
    origem = client.get("/api/tactics/next").json()["id"]
    p_origem = client.post(f"/api/tactics/{origem}/save").json()
    outro = client.get(f"/api/tactics/next?exclude={origem}").json()["id"]
    r = client.post(f"/api/tactics/{outro}/save", json={"correct": True, "sibling_of": p_origem["id"]})
    assert r.status_code == 201 and r.json()["sibling_of"] == p_origem["id"]
    assert client.post(f"/api/tactics/{outro}/save", json={"sibling_of": "nao-existe"}).status_code == 404


def test_salvar_tatica_com_sibling_tier(client):
    """`sibling_tier` (o degrau da cascata que trouxe o irmão) grava junto de `sibling_of`,
    do mesmo jeito e sem exigir um exercício existente (spec golpes trechos §6)."""
    run_import(client)
    assert client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50}).status_code == 200
    origem = client.get("/api/tactics/next").json()["id"]
    p_origem = client.post(f"/api/tactics/{origem}/save").json()
    outro = client.get(f"/api/tactics/next?exclude={origem}").json()["id"]
    r = client.post(f"/api/tactics/{outro}/save",
                    json={"correct": True, "sibling_of": p_origem["id"], "sibling_tier": "trecho2"})
    assert r.status_code == 201 and r.json()["sibling_tier"] == "trecho2"


def test_salvar_de_novo_com_sibling_tier_completa_o_dado_que_faltava(client):
    run_import(client)
    assert client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50}).status_code == 200
    origem = client.get("/api/tactics/next").json()["id"]
    p_origem = client.post(f"/api/tactics/{origem}/save").json()
    outro = client.get(f"/api/tactics/next?exclude={origem}").json()["id"]

    sem_vinculo = client.post(f"/api/tactics/{outro}/save").json()
    assert sem_vinculo["sibling_tier"] is None

    completo = client.post(f"/api/tactics/{outro}/save", json={"sibling_of": p_origem["id"], "sibling_tier": "espelho"})
    assert completo.status_code == 200 and completo.json()["sibling_tier"] == "espelho"
    # não sobrescreve um degrau já gravado
    outra_vez = client.post(f"/api/tactics/{outro}/save", json={"sibling_tier": "esqueleto"})
    assert outra_vez.json()["sibling_tier"] == "espelho"
