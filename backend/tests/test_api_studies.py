"""Testes das rotas de estudos: importação, detalhe, fila e remoção."""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from chess_trainer.api.app import create_app
from chess_trainer.core.models import Puzzle
from tests.fakes import FakeEngine, first_legal_default

FIXTURE = Path(__file__).parent / "fixtures" / "study_4JKVAfaE.pgn"
PGN = FIXTURE.read_text(encoding="utf-8")
URL = "https://lichess.org/study/4JKVAfaE"

# estudo colado sem `ChapterURL`: fica sem id do Lichess, então não dá para reimportar
PGN_SEM_URL = """[Event "Colado: Único"]
[Result "*"]
[StudyName "Colado"]
[ChapterName "Único"]
[ChapterMode "gamebook"]
[SetUp "1"]
[FEN "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"]

1. Ra8# *
"""

# dois capítulos com a mesma posição inicial: o segundo não vira exercício
PGN_FEN_REPETIDA = """[Event "Repetido: Um"]
[Result "*"]
[StudyName "Repetido"]
[ChapterName "Um"]
[ChapterMode "gamebook"]
[SetUp "1"]
[FEN "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"]

1. Ra8# *

[Event "Repetido: Dois"]
[Result "*"]
[StudyName "Repetido"]
[ChapterName "Dois"]
[ChapterMode "gamebook"]
[SetUp "1"]
[FEN "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"]

1. Ra7 Kf8 2. Rb7 *
"""


def build_client(handler):
    app = create_app(
        db_path=":memory:",
        engine_factory=lambda s: FakeEngine(default=first_legal_default(0)),
        study_http_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return TestClient(app)


def handler_ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/study/4JKVAfaE.pgn":
        return httpx.Response(200, text=PGN)
    return httpx.Response(404, text="")


@pytest.fixture
def client():
    with build_client(handler_ok) as c:
        yield c


def esperar_job(client) -> dict:
    client.app.state.jobs.wait()
    return client.get("/api/status").json()["job"]


def importar(client, body=None) -> dict:
    r = client.post("/api/studies/import", json=body or {"url": URL})
    assert r.status_code == 202, r.json()
    job = esperar_job(client)
    assert job["state"] == "idle", job
    return job


# --- importação ----------------------------------------------------------


def test_importar_por_url_lista_o_estudo(client):
    job = importar(client)
    assert job["job"] == "import_study"
    assert job["message"] == "27 capítulos, 15 exercícios, 0 pulados"

    estudos = client.get("/api/studies").json()
    assert len(estudos) == 1
    estudo = estudos[0]
    assert estudo["lichess_id"] == "4JKVAfaE" and estudo["author"] == "basso01"
    assert estudo["title"].startswith("#PL05A") and estudo["source_url"] == URL
    assert estudo["chapter_count"] == 27 and estudo["in_queue"] == 15 and estudo["due_today"] == 0
    assert estudo["imported_at"] is not None


def test_detalhe_traz_os_capitulos_em_ordem(client):
    importar(client)
    estudo_id = client.get("/api/studies").json()[0]["id"]

    detalhe = client.get(f"/api/studies/{estudo_id}").json()
    capitulos = detalhe["chapters"]
    assert detalhe["chapters"] and len(capitulos) == 27
    assert [c["order"] for c in capitulos] == list(range(1, 28))
    primeiro = capitulos[0]
    assert primeiro["mode"] == "gamebook" and primeiro["puzzle_id"] and primeiro["in_queue"] is True
    assert primeiro["lichess_url"].startswith("https://lichess.org/study/4JKVAfaE/")
    assert sum(1 for c in capitulos if c["mode"] == "read") == 12


def test_fila_filtrada_pelo_estudo(client):
    importar(client)
    estudo_id = client.get("/api/studies").json()[0]["id"]

    fila = client.get("/api/queue", params={"study_id": estudo_id}).json()
    assert fila["new_available"] == 15 and fila["items"]
    assert all(item["source"] == "study" for item in fila["items"])
    assert fila["items"][0]["study"]["id"] == estudo_id
    assert fila["items"][0]["study"]["chapter_name"]


def test_mensagem_final_nomeia_o_capitulo_pulado(client):
    job = importar(client, {"pgn": PGN_FEN_REPETIDA})

    assert job["message"].startswith("2 capítulos, 1 exercícios, 1 pulados: ")
    assert "2. Dois: posição inicial já usada por outro capítulo" in job["message"]


def test_contagem_da_repeticao_ignora_exercicio_travado(client):
    importar(client)
    with client.app.state.session_factory() as db:
        travado = db.scalars(select(Puzzle).where(Puzzle.source == "study")).first()
        travado.is_leech = True
        db.commit()

    estudo = client.get("/api/studies").json()[0]
    assert estudo["in_queue"] == 14


def test_importar_por_pgn_nao_baixa_nada():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("não deveria baixar nada quando o PGN vem no corpo")

    with build_client(handler) as client:
        importar(client, {"pgn": PGN})
        assert client.get("/api/studies").json()[0]["chapter_count"] == 27


def test_url_invalida_400(client):
    r = client.post("/api/studies/import", json={"url": "lixo"})
    assert r.status_code == 400 and r.json()["detail"] == "URL de estudo inválida"


def test_sem_url_e_sem_pgn_400(client):
    r = client.post("/api/studies/import", json={})
    assert r.status_code == 400 and r.json()["detail"] == "informe a URL do estudo ou o PGN"


def test_estudo_privado_termina_o_job_em_erro():
    with build_client(lambda request: httpx.Response(404, text="")) as client:
        assert client.post("/api/studies/import", json={"url": URL}).status_code == 202
        job = esperar_job(client)
        assert job["state"] == "error"
        assert job["error"] == "estudo privado ou inexistente; exporte o PGN no Lichess e cole aqui"
        assert client.get("/api/studies").json() == []


def test_importacao_com_outra_tarefa_em_andamento_409(client):
    import threading

    gate = threading.Event()
    client.app.state.jobs.submit("import", lambda progress: gate.wait(5))
    try:
        assert client.post("/api/studies/import", json={"url": URL}).status_code == 409
    finally:
        gate.set()
        client.app.state.jobs.wait()


# --- reimportação --------------------------------------------------------


def test_reimportar_nao_duplica(client):
    importar(client)
    estudo_id = client.get("/api/studies").json()[0]["id"]

    assert client.post(f"/api/studies/{estudo_id}/reimport").status_code == 202
    job = esperar_job(client)
    assert job["state"] == "idle", job

    estudos = client.get("/api/studies").json()
    assert len(estudos) == 1 and estudos[0]["chapter_count"] == 27 and estudos[0]["id"] == estudo_id


def test_reimportar_sem_id_do_lichess_400(client):
    importar(client, {"pgn": PGN_SEM_URL})
    estudo = client.get("/api/studies").json()[0]
    assert estudo["lichess_id"] is None

    r = client.post(f"/api/studies/{estudo['id']}/reimport")
    assert r.status_code == 400 and "PGN" in r.json()["detail"]


def test_estudo_inexistente_404(client):
    assert client.get("/api/studies/nada").status_code == 404
    assert client.post("/api/studies/nada/reimport").status_code == 404
    assert client.post("/api/studies/nada/queue", json={"in_queue": False}).status_code == 404
    assert client.delete("/api/studies/nada").status_code == 404


# --- fila e remoção ------------------------------------------------------


def test_tirar_e_devolver_o_estudo_da_repeticao(client):
    importar(client)
    estudo_id = client.get("/api/studies").json()[0]["id"]

    fora = client.post(f"/api/studies/{estudo_id}/queue", json={"in_queue": False})
    assert fora.status_code == 200 and fora.json()["in_queue"] == 0
    assert client.get("/api/queue", params={"study_id": estudo_id}).json()["items"] == []

    dentro = client.post(f"/api/studies/{estudo_id}/queue", json={"in_queue": True})
    assert dentro.status_code == 200 and dentro.json()["in_queue"] == 15
    assert client.get("/api/queue", params={"study_id": estudo_id}).json()["items"]


def test_remover_o_estudo_apaga_os_exercicios(client):
    importar(client)
    estudo_id = client.get("/api/studies").json()[0]["id"]
    assert client.get("/api/dashboard").json()["by_source"]["study"]["in_queue"] == 15

    assert client.delete(f"/api/studies/{estudo_id}").status_code == 204

    assert client.get("/api/studies").json() == []
    assert client.get(f"/api/studies/{estudo_id}").status_code == 404
    assert client.get("/api/dashboard").json()["by_source"]["study"]["in_queue"] == 0
