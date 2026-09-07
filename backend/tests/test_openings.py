"""Testes do livro de aberturas: normalização, cache, erros e a rota /api/openings."""

import httpx
import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.openings import (
    MSG_INDISPONIVEL,
    MSG_LIMITE,
    MSG_SEM_TOKEN,
    MSG_TOKEN_RECUSADO,
    OpeningExplorer,
    OpeningsError,
)
from tests.fakes import FakeEngine, first_legal_default

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
TOKEN = "lip_tokenDeTeste"

# resposta real do explorador (mestres), reduzida; e4 aparece antes de d4 mesmo
# tendo menos partidas, para o teste cobrir a ordenação
MASTERS = {
    "white": 120,
    "draws": 60,
    "black": 20,
    "moves": [
        {"uci": "e2e4", "san": "e4", "averageRating": 2503, "white": 30, "draws": 20, "black": 10},
        {"uci": "d2d4", "san": "d4", "averageRating": 2481, "white": 60, "draws": 30, "black": 10},
    ],
    "topGames": [],
    "opening": {"eco": "A00", "name": "Início"},
}


def make_explorer(handler, **kwargs) -> OpeningExplorer:
    return OpeningExplorer(lambda: httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)


def ok_handler(calls: list[httpx.Request], payload=MASTERS):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    return handler


def status_handler(status: int, **kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "x"}, **kwargs)

    return handler


# --- chamada e normalização ---------------------------------------------


def test_mestres_url_cabecalhos_e_normalizacao():
    calls: list[httpx.Request] = []
    data = make_explorer(ok_handler(calls)).fetch(FEN, "masters", TOKEN)

    (req,) = calls
    assert str(req.url).startswith("https://explorer.lichess.ovh/masters?")
    assert req.url.params["fen"] == FEN and req.url.params["topGames"] == "0"
    assert req.headers["authorization"] == f"Bearer {TOKEN}"
    assert req.headers["user-agent"] == "chess-trainer/0.1"
    assert req.headers["accept"] == "application/json"

    assert data["opening"] == {"eco": "A00", "name": "Início"}
    assert (data["total"], data["white"], data["draws"], data["black"]) == (200, 120, 60, 20)
    # ordenado por número de partidas, do maior para o menor
    assert [m["san"] for m in data["moves"]] == ["d4", "e4"]
    assert data["moves"][0] == {
        "uci": "d2d4", "san": "d4", "games": 100,
        "white": 60, "draws": 30, "black": 10, "avg_rating": 2481,
    }


def test_jogadores_manda_variante_ritmos_e_ratings():
    calls: list[httpx.Request] = []
    make_explorer(ok_handler(calls)).fetch(FEN, "lichess", TOKEN)

    (req,) = calls
    assert str(req.url).startswith("https://explorer.lichess.ovh/lichess?")
    assert req.url.params["variant"] == "standard"
    assert req.url.params["speeds"] == "rapid,classical"
    assert req.url.params["ratings"] == "1600,1800,2000,2200,2500"
    assert req.url.params["fen"] == FEN
    assert req.url.params["topGames"] == "0" and req.url.params["recentGames"] == "0"


def test_sem_abertura_e_sem_lances():
    vazio = {"white": 0, "draws": 0, "black": 0, "moves": [], "topGames": [], "opening": None}
    data = make_explorer(ok_handler([], vazio)).fetch(FEN, "masters", TOKEN)
    assert data == {"opening": None, "total": 0, "white": 0, "draws": 0, "black": 0, "moves": []}


def test_lance_sem_rating_medio_vira_none():
    payload = {"white": 1, "draws": 0, "black": 0, "opening": None,
               "moves": [{"uci": "e2e4", "san": "e4", "white": 1, "draws": 0, "black": 0}]}
    data = make_explorer(ok_handler([], payload)).fetch(FEN, "masters", TOKEN)
    assert data["moves"][0]["avg_rating"] is None


# --- erros ---------------------------------------------------------------


def test_sem_token_nao_chama_a_api():
    calls: list[httpx.Request] = []
    with pytest.raises(OpeningsError) as exc:
        make_explorer(ok_handler(calls)).fetch(FEN, "masters", "   ")
    assert exc.value.status == 400 and exc.value.message == MSG_SEM_TOKEN
    assert calls == []


@pytest.mark.parametrize("status", [401, 403])
def test_token_recusado(status):
    with pytest.raises(OpeningsError) as exc:
        make_explorer(status_handler(status)).fetch(FEN, "masters", TOKEN)
    assert exc.value.status == 400 and exc.value.message == MSG_TOKEN_RECUSADO


def test_limite_de_requisicoes():
    with pytest.raises(OpeningsError) as exc:
        make_explorer(status_handler(429)).fetch(FEN, "masters", TOKEN)
    assert exc.value.status == 503 and exc.value.message == MSG_LIMITE


@pytest.mark.parametrize("status", [404, 500, 503])
def test_outros_erros_viram_502(status):
    with pytest.raises(OpeningsError) as exc:
        make_explorer(status_handler(status)).fetch(FEN, "masters", TOKEN)
    assert exc.value.status == 502 and exc.value.message == MSG_INDISPONIVEL


def test_timeout_vira_502():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("tempo esgotado", request=request)

    with pytest.raises(OpeningsError) as exc:
        make_explorer(handler).fetch(FEN, "masters", TOKEN)
    assert exc.value.status == 502 and exc.value.message == MSG_INDISPONIVEL


def test_resposta_que_nao_e_json_vira_502():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>manutenção</html>")

    with pytest.raises(OpeningsError) as exc:
        make_explorer(handler).fetch(FEN, "masters", TOKEN)
    assert exc.value.status == 502


def test_erro_nunca_carrega_o_token():
    with pytest.raises(OpeningsError) as exc:
        make_explorer(status_handler(401)).fetch(FEN, "masters", TOKEN)
    assert TOKEN not in str(exc.value)


# --- cache ---------------------------------------------------------------


def test_cache_por_base_e_fen():
    calls: list[httpx.Request] = []
    explorer = make_explorer(ok_handler(calls))
    primeira = explorer.fetch(FEN, "masters", TOKEN)
    segunda = explorer.fetch(FEN, "masters", TOKEN)
    assert primeira == segunda and len(calls) == 1

    explorer.fetch(FEN, "lichess", TOKEN)  # outra base: chamada nova
    assert len(calls) == 2
    outra_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    explorer.fetch(outra_fen, "masters", TOKEN)
    assert len(calls) == 3


def test_cache_expira_com_o_ttl():
    calls: list[httpx.Request] = []
    agora = [0.0]
    explorer = make_explorer(ok_handler(calls), ttl_s=100.0, clock=lambda: agora[0])
    explorer.fetch(FEN, "masters", TOKEN)
    agora[0] = 99.0
    explorer.fetch(FEN, "masters", TOKEN)
    assert len(calls) == 1
    agora[0] = 101.0
    explorer.fetch(FEN, "masters", TOKEN)
    assert len(calls) == 2


def test_cache_descarta_a_entrada_menos_usada():
    calls: list[httpx.Request] = []
    explorer = make_explorer(ok_handler(calls), max_entries=2)
    a, b, c = "fen-a", "fen-b", "fen-c"
    explorer.fetch(a, "masters", TOKEN)
    explorer.fetch(b, "masters", TOKEN)
    explorer.fetch(a, "masters", TOKEN)  # `a` volta a ser a mais recente
    assert len(calls) == 2
    explorer.fetch(c, "masters", TOKEN)  # passa de 2: sai `b`
    assert len(calls) == 3
    explorer.fetch(a, "masters", TOKEN)
    assert len(calls) == 3
    explorer.fetch(b, "masters", TOKEN)
    assert len(calls) == 4


def test_cache_nao_guarda_erro():
    respostas = [httpx.Response(429, json={}), httpx.Response(200, json=MASTERS)]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return respostas.pop(0)

    explorer = make_explorer(handler)
    with pytest.raises(OpeningsError):
        explorer.fetch(FEN, "masters", TOKEN)
    assert explorer.fetch(FEN, "masters", TOKEN)["total"] == 200
    assert len(calls) == 2


def test_mexer_no_resultado_nao_estraga_o_cache():
    explorer = make_explorer(ok_handler([]))
    primeira = explorer.fetch(FEN, "masters", TOKEN)
    primeira["moves"].clear()
    assert len(explorer.fetch(FEN, "masters", TOKEN)["moves"]) == 2


# --- rota ----------------------------------------------------------------


def build_client(handler) -> TestClient:
    app = create_app(
        db_path=":memory:",
        engine_factory=lambda s: FakeEngine(default=first_legal_default(0)),
        openings_http_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return TestClient(app)


def com_token(client: TestClient) -> TestClient:
    assert client.put("/api/settings", json={"lichess_token": TOKEN}).status_code == 200
    return client


def test_rota_devolve_o_livro():
    client = com_token(build_client(ok_handler([])))
    r = client.get("/api/openings", params={"fen": FEN})
    assert r.status_code == 200
    body = r.json()
    assert body["opening"]["name"] == "Início" and body["total"] == 200
    assert [m["san"] for m in body["moves"]] == ["d4", "e4"]


def test_rota_base_padrao_e_mestres():
    calls: list[httpx.Request] = []
    client = com_token(build_client(ok_handler(calls)))
    client.get("/api/openings", params={"fen": FEN})
    assert calls[0].url.path == "/masters"
    client.get("/api/openings", params={"fen": FEN, "db": "lichess"})
    assert calls[1].url.path == "/lichess"


def test_rota_recusa_base_desconhecida():
    client = com_token(build_client(ok_handler([])))
    assert client.get("/api/openings", params={"fen": FEN, "db": "chesscom"}).status_code == 422


def test_rota_recusa_fen_invalida():
    calls: list[httpx.Request] = []
    client = com_token(build_client(ok_handler(calls)))
    r = client.get("/api/openings", params={"fen": "nao é uma fen"})
    assert r.status_code == 400 and r.json()["detail"] == "FEN inválida"
    assert calls == []


def test_rota_sem_token():
    client = build_client(ok_handler([]))
    r = client.get("/api/openings", params={"fen": FEN})
    assert r.status_code == 400 and r.json()["detail"] == MSG_SEM_TOKEN


def test_rota_token_recusado():
    client = com_token(build_client(status_handler(401)))
    r = client.get("/api/openings", params={"fen": FEN})
    assert r.status_code == 400 and r.json()["detail"] == MSG_TOKEN_RECUSADO


def test_rota_limite_do_lichess():
    client = com_token(build_client(status_handler(429)))
    r = client.get("/api/openings", params={"fen": FEN})
    assert r.status_code == 503 and r.json()["detail"] == MSG_LIMITE


def test_rota_explorador_fora_do_ar():
    client = com_token(build_client(status_handler(500)))
    r = client.get("/api/openings", params={"fen": FEN})
    assert r.status_code == 502 and r.json()["detail"] == MSG_INDISPONIVEL


def test_rota_usa_o_cache():
    calls: list[httpx.Request] = []
    client = com_token(build_client(ok_handler(calls)))
    assert client.get("/api/openings", params={"fen": FEN}).status_code == 200
    assert client.get("/api/openings", params={"fen": FEN}).status_code == 200
    assert len(calls) == 1


def test_cache_ignora_contadores_de_lances(explorer_factory=None):
    from chess_trainer.core.openings import OpeningExplorer
    import httpx
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"white": 1, "draws": 0, "black": 0, "moves": [], "opening": None})

    ex = OpeningExplorer(lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    base = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"
    ex.fetch(f"{base} 0 1", "masters", token="t")
    ex.fetch(f"{base} 3 12", "masters", token="t")
    assert len(calls) == 1


def test_base_desconhecida_e_recusada():
    from chess_trainer.core.openings import OpeningExplorer
    import httpx
    import pytest
    ex = OpeningExplorer(lambda: httpx.Client())
    with pytest.raises(ValueError):
        ex.fetch("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "../x", token="t")
