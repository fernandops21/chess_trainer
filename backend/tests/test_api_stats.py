from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.models import LichessPuzzle, Review, TacticsAttempt, utcnow
from chess_trainer.core.srs.queue import local_day, local_day_start
from tests.factories import make_puzzle

FEN = "8/8/8/8/8/8/8/K6k w - - 0 1"


def _review(db, puzzle, *, ok: bool, at, dica: bool = False):
    db.add(Review(puzzle_id=puzzle.id, result="correct" if ok else "wrong", ease=2.5,
                  interval_days=1, due_at=at, lapses=0, reviewed_at=at, used_hint=dica))


@pytest.fixture
def client_com_dados(tmp_path):
    """App com revisões em 3 dias e 2 fontes, mais 3 tentativas de tática."""
    app = create_app(db_path=str(tmp_path / "stats.db"))
    db = app.state.session_factory()
    now = utcnow()
    proprio = make_puzzle(db, fen="r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", theme="fork")
    estudo = make_puzzle(db, fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", theme="pin")
    estudo.source = "study"
    db.commit()
    # hoje: 2 certas (uma de cada fonte) e 1 certa com dica, que não conta como acerto;
    # ontem: 1 errada; anteontem: 1 certa e 1 errada
    _review(db, proprio, ok=True, at=now)
    _review(db, proprio, ok=True, at=now, dica=True)
    _review(db, estudo, ok=True, at=now)
    _review(db, proprio, ok=False, at=now - timedelta(days=1))
    _review(db, proprio, ok=True, at=now - timedelta(days=2))
    _review(db, estudo, ok=False, at=now - timedelta(days=2))
    # fora do período de 30 dias pedido no teste
    _review(db, proprio, ok=True, at=now - timedelta(days=200))
    db.add(LichessPuzzle(id="l1", fen=FEN, moves="a1a2 h1h2", rating=1200, rating_deviation=50,
                         popularity=90, nb_plays=500, themes="fork middlegame", opening_tags=""))
    for dias, depois in ((3, 1516), (2, 1532), (1, 1520)):
        db.add(TacticsAttempt(puzzle_id="l1", correct=depois > 1516, rating_before=1500,
                              rating_after=depois, puzzle_rating=1200, attempted_at=now - timedelta(days=dias)))
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c, now


def test_progresso_agrupa_por_dia_fonte_e_ordena_o_rating(client_com_dados):
    client, now = client_com_dados
    p = client.get("/api/stats/progress", params={"days": 30}).json()

    dias = p["reviews_per_day"]
    assert [d["day"] for d in dias] == sorted(d["day"] for d in dias)  # ordem cronológica
    assert len(dias) == 3  # só os dias com revisão; o de 200 dias atrás ficou de fora
    hoje = local_day(now).isoformat()
    # a certa com dica entra como "wrong": acertar com dica não é acerto (igual a `theme_stats`)
    assert dias[-1] == {"day": hoje, "correct": 2, "wrong": 1}
    assert dias[0]["correct"] == 1 and dias[0]["wrong"] == 1
    assert dias[1] == {"day": local_day(now - timedelta(days=1)).isoformat(), "correct": 0, "wrong": 1}

    assert p["by_source"]["own"] == {"reviews": 4, "correct": 2}
    assert p["by_source"]["study"] == {"reviews": 2, "correct": 1}
    assert p["by_source"]["lichess"] == {"reviews": 0, "correct": 0}  # sempre as três chaves

    assert [ponto["rating"] for ponto in p["tactics_rating"]] == [1516, 1532, 1520]
    assert p["tactics_rating"][0]["at"] < p["tactics_rating"][-1]["at"]

    assert p["totals"] == {"reviews": 6, "correct": 3, "puzzles_in_queue": 2}
    assert p["streak_days"] == 3


def test_progresso_com_janela_curta_e_banco_vazio(client_com_dados):
    client, _ = client_com_dados
    # 1 dia: só as revisões de hoje entram, mas a sequência continua olhando tudo
    p = client.get("/api/stats/progress", params={"days": 1}).json()
    assert len(p["reviews_per_day"]) == 1 and p["totals"]["reviews"] == 3 and p["streak_days"] == 3
    assert client.get("/api/stats/progress", params={"days": 0}).status_code == 422

    vazio = TestClient(create_app(db_path=":memory:")).get("/api/stats/progress").json()
    assert vazio["reviews_per_day"] == [] and vazio["tactics_rating"] == []
    assert vazio["streak_days"] == 0 and vazio["totals"]["reviews"] == 0
    assert set(vazio["by_source"]) == {"own", "lichess", "study"}


def test_progresso_conta_o_dia_mais_antigo_inteiro(tmp_path):
    """O período começa na meia-noite local do dia mais antigo, não no instante de agora."""
    app = create_app(db_path=str(tmp_path / "borda.db"))
    db = app.state.session_factory()
    now = utcnow()
    puzzle = make_puzzle(db, fen="r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    # com days=3 o dia mais antigo do período é anteontem: a revisão feita logo depois
    # da meia-noite local dele conta; a do segundo anterior já é do dia de fora
    inicio = local_day_start(now) - timedelta(days=2)
    _review(db, puzzle, ok=True, at=inicio)
    _review(db, puzzle, ok=False, at=inicio - timedelta(seconds=1))
    db.commit()
    db.close()

    with TestClient(app) as client:
        p = client.get("/api/stats/progress", params={"days": 3}).json()
    assert [d["day"] for d in p["reviews_per_day"]] == [local_day(inicio).isoformat()]
    assert p["reviews_per_day"][0] == {"day": local_day(inicio).isoformat(), "correct": 1, "wrong": 0}
    assert p["totals"]["reviews"] == 1
