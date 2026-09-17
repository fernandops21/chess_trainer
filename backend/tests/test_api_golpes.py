import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.models import LichessPuzzle
from tests.fakes import FakeEngine, first_legal_default

FEN_PASTOR_ANTES = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 4 4"


def pastor(pid, rating=800):
    return LichessPuzzle(id=pid, fen=FEN_PASTOR_ANTES, moves="g8f6 h5f7", rating=rating, rating_deviation=50,
                         popularity=90, nb_plays=500, themes="mateIn1", opening_tags="")


@pytest.fixture
def client():
    app = create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)))
    with TestClient(app) as c:
        db = app.state.session_factory()
        for i in range(6):
            db.add(pastor(f"p{i}", 700 + 100 * i))
        db.commit(); db.close()
        yield c


def test_status_e_preparar(client):
    s = client.get("/api/golpes/status").json()
    assert s["enabled"] is True and s["versao"] == 1 and s["assinados"] == 0 and s["cobertura"] is None and s["rotulagem"] is False
    assert client.post("/api/golpes/preparar").status_code == 202
    client.app.state.jobs.wait()
    assert client.get("/api/status").json()["job"]["state"] == "idle"
    s = client.get("/api/golpes/status").json()
    assert s["assinados"] == 6 and s["cobertura"]["destinos"]["ge5"] == 6


def test_desligado_da_404(client):
    assert client.put("/api/settings", json={"golpes_enabled": False}).status_code == 200
    assert client.post("/api/golpes/preparar").status_code == 404
    assert client.get("/api/golpes/status").json()["enabled"] is False


def test_settings_validam_o_bloco(client):
    assert client.put("/api/settings", json={"golpes_bloco": 2}).status_code == 422
    assert client.put("/api/settings", json={"golpes_bloco": 7}).status_code == 200
    assert client.get("/api/settings").json()["golpes_bloco"] == 7
