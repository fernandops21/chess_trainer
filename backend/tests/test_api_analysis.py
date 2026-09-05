import chess
import chess.engine
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.analysis.interactive import InteractiveAnalyzer
from chess_trainer.core.evals import MATE_SCORE
from tests.fakes import FakeEngine, first_legal_default

MATE_IN_1 = "6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1"


def _engine():
    return FakeEngine({chess.Board(MATE_IN_1).epd(): [LineEval("a1a8", MATE_SCORE - 1, ("a1a8",))]}, first_legal_default(20))


def test_analyzer_lines_with_san_and_cache():
    fake = _engine()
    az = InteractiveAnalyzer(lambda: fake, depth=8, max_seconds=1.0)
    r = az.analyse(MATE_IN_1)
    assert r["turn"] == "white" and r["terminal"] is None
    assert r["lines"][0]["move"] == "a1a8" and r["lines"][0]["san"] == "Ra8#" and r["lines"][0]["score"] == MATE_SCORE - 1
    assert r["lines"][0]["pv_san"] == ["Ra8#"]
    az.analyse(MATE_IN_1)
    assert len(fake.calls) == 1            # cache
    assert fake.max_seconds[0] == 1.0 and fake.depths[0] == 8


def test_analyzer_terminal_and_invalid():
    import pytest
    az = InteractiveAnalyzer(lambda: _engine())
    mated = az.analyse("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert mated["terminal"] == "checkmate" and mated["lines"] == []
    with pytest.raises(ValueError):
        az.analyse("isto nao e fen")


def test_analyse_route():
    app = create_app(db_path=":memory:", analysis_engine_factory=lambda: _engine())
    client = TestClient(app)
    r = client.post("/api/analyse", json={"fen": MATE_IN_1})
    assert r.status_code == 200 and r.json()["lines"][0]["san"] == "Ra8#"
    assert client.post("/api/analyse", json={"fen": "xx"}).status_code == 400
    assert client.post("/api/analyse", json={"fen": MATE_IN_1, "multipv": 9}).status_code == 422


def test_analyse_route_without_engine_is_503():
    client = TestClient(create_app(db_path=":memory:", analysis_engine_factory=lambda: None))
    assert client.post("/api/analyse", json={"fen": MATE_IN_1}).status_code == 503


class _ClosableFakeEngine(FakeEngine):
    """FakeEngine que registra se `close()` foi chamado, para checar o shutdown do app."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_app_shutdown_closes_interactive_engine():
    fake = _ClosableFakeEngine({chess.Board(MATE_IN_1).epd(): [LineEval("a1a8", MATE_SCORE - 1, ("a1a8",))]})
    app = create_app(db_path=":memory:", analysis_engine_factory=lambda: fake)
    with TestClient(app) as client:
        r = client.post("/api/analyse", json={"fen": MATE_IN_1})
        assert r.status_code == 200
        assert fake.closed is False
    assert fake.closed is True  # engine fechada no shutdown do lifespan


def test_analyse_route_empty_lines_is_503_and_recreates_engine():
    creations = {"n": 0}

    def factory():
        creations["n"] += 1
        return FakeEngine(default=lambda board: [])  # engine "viva" mas sem nenhuma linha

    app = create_app(db_path=":memory:", analysis_engine_factory=factory)
    client = TestClient(app)
    r = client.post("/api/analyse", json={"fen": MATE_IN_1})
    assert r.status_code == 503
    assert creations["n"] == 1

    r = client.post("/api/analyse", json={"fen": MATE_IN_1})
    assert r.status_code == 503
    assert creations["n"] == 2  # engine anterior descartada: reinvoca a factory


def test_analyse_route_invalid_but_parseable_fen_is_400():
    app = create_app(db_path=":memory:", analysis_engine_factory=lambda: _engine())
    client = TestClient(app)
    r = client.post("/api/analyse", json={"fen": "8/8/8/8/8/8/8/8 w - - 0 1"})  # sem os reis
    assert r.status_code == 400


def test_analyzer_recreates_engine_after_engine_error():
    import pytest

    creations = {"n": 0}

    def factory():
        creations["n"] += 1
        fake = _engine()
        if creations["n"] == 1:
            fake.fail_next = True  # a primeira engine criada "morre" na primeira análise
        return fake

    az = InteractiveAnalyzer(factory, depth=8, max_seconds=1.0)

    with pytest.raises(chess.engine.EngineError):
        az.analyse(MATE_IN_1)
    assert creations["n"] == 1  # ainda não recriou sozinha

    r = az.analyse(MATE_IN_1)  # próxima chamada: engine morta descartada, cria uma nova

    assert creations["n"] == 2
    assert r["lines"][0]["move"] == "a1a8"
