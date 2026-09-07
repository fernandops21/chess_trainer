"""Testes das rotas de estudos: importação, detalhe, edição, exportação, fila e remoção."""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from chess_trainer.api.app import create_app
from chess_trainer.core.models import Puzzle, Review, utcnow
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


# estudo sem nenhum capítulo em modo gamebook: importa, mas não cria exercício algum
PGN_SO_LEITURA = """[Event "Leitura: Um"]
[Result "*"]
[StudyName "Leitura"]
[ChapterName "Um"]

1. e4 e5 *
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


def test_mensagem_final_avisa_quando_nao_ha_exercicio(client):
    """Só capítulos de leitura: "0 exercícios" sozinho parece falha da importação."""
    job = importar(client, {"pgn": PGN_SO_LEITURA})

    assert job["message"] == "1 capítulos, 0 exercícios, 0 pulados (só capítulos de leitura; nenhum exercício)"
    estudo = client.get("/api/studies").json()[0]
    assert estudo["chapter_count"] == 1 and estudo["exercise_count"] == 0 and estudo["in_queue"] == 0


def test_cancelar_a_importacao_nao_grava_capitulo_nenhum(client):
    """Cancelar antes do commit descarta o estudo inteiro: nada de meia importação."""
    from chess_trainer.core.models import Study, StudyChapter

    client.app.state.jobs.should_stop = lambda: True

    assert client.post("/api/studies/import", json={"url": URL}).status_code == 202
    job = esperar_job(client)

    assert job["state"] == "idle" and job["message"] == "cancelado"
    assert client.get("/api/studies").json() == []
    with client.app.state.session_factory() as db:
        assert db.scalars(select(Study)).all() == []
        assert db.scalars(select(StudyChapter)).all() == []
        assert db.scalars(select(Puzzle)).all() == []


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


# --- criação e edição local ----------------------------------------------

# mate no corredor: a torre em a1 dá mate em um lance
FEN_MATE = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
# peão passado: dois lances do solucionador, sem mate
FEN_PEAO = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"

ARVORE_MATE = {
    "fen": FEN_MATE,
    "orientation": "white",
    "intro": "Mate em um.",
    "root": {
        "shapes": [{"orig": "a1", "dest": "a8", "brush": "green"}],
        "children": [
            {"id": "n1", "uci": "a1a8", "san": "Ra8#", "comment": "Mate!",
             "shapes": [], "nags": [], "children": []},
            {"id": "n2", "uci": "a1a7", "san": "Ra7", "comment": "Deixa o rei escapar.",
             "shapes": [{"orig": "g8", "brush": "red"}], "nags": [2], "children": []},
        ],
    },
}

ARVORE_PEAO = {
    "fen": FEN_PEAO,
    "orientation": "white",
    "intro": "A marcha do peão.",
    "root": {"shapes": [], "children": [
        {"id": "n1", "uci": "e2e4", "san": "e4", "comment": "", "shapes": [], "nags": [], "children": [
            {"id": "n2", "uci": "e8d7", "san": "Kd7", "comment": "", "shapes": [], "nags": [], "children": [
                {"id": "n3", "uci": "e4e5", "san": "e5", "comment": "Segue em frente.",
                 "shapes": [], "nags": [], "children": []},
            ]},
        ]},
    ]},
}


def criar_estudo(client, title="Meu estudo", author="eu") -> dict:
    r = client.post("/api/studies", json={"title": title, "author": author})
    assert r.status_code == 201, r.text
    return r.json()


def criar_capitulo(client, estudo_id, **body) -> dict:
    r = client.post(f"/api/studies/{estudo_id}/chapters", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def salvar_capitulo(client, estudo_id, cid, tree, name="Um", mode="gamebook", orientation="white"):
    return client.put(f"/api/studies/{estudo_id}/chapters/{cid}",
                      json={"name": name, "mode": mode, "orientation": orientation, "tree": tree})


def arvores(client, estudo_id) -> list[tuple]:
    """(nome, modo, árvore) de cada capítulo, para comparar dois estudos."""
    detalhe = client.get(f"/api/studies/{estudo_id}").json()
    saida = []
    for capitulo in detalhe["chapters"]:
        dados = client.get(f"/api/studies/{estudo_id}/chapters/{capitulo['id']}").json()
        saida.append((dados["name"], dados["mode"], dados["tree"]))
    return saida


def test_criar_estudo_local(client):
    estudo = criar_estudo(client, "Táticas do Basso", "professor")

    assert estudo["origin"] == "local" and estudo["lichess_id"] is None
    assert estudo["title"] == "Táticas do Basso" and estudo["author"] == "professor"
    assert estudo["chapter_count"] == 0 and estudo["updated_at"] is not None
    assert client.get("/api/studies").json()[0]["id"] == estudo["id"]


def test_criar_capitulo_devolve_o_detalhe_com_a_arvore(client):
    estudo = criar_estudo(client)

    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE,
                              orientation="black", mode="gamebook")

    assert capitulo["order"] == 1 and capitulo["name"] == "Um" and capitulo["mode"] == "gamebook"
    assert capitulo["fen"] == FEN_MATE and capitulo["orientation"] == "black"
    assert capitulo["tree"]["root"]["children"] == [] and capitulo["puzzle_id"] is None
    assert capitulo["updated_at"] is not None and "[FEN " in capitulo["pgn"]
    assert client.get(f"/api/studies/{estudo['id']}").json()["chapters"][0]["id"] == capitulo["id"]


def test_criar_capitulo_com_fen_invalida_422(client):
    estudo = criar_estudo(client)

    r = client.post(f"/api/studies/{estudo['id']}/chapters", json={"name": "Torto", "fen": "nada"})

    assert r.status_code == 422
    assert any("FEN inválida" in erro for erro in r.json()["detail"])


def test_salvar_o_capitulo_cria_o_exercicio(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE, mode="gamebook")

    r = salvar_capitulo(client, estudo["id"], capitulo["id"], ARVORE_MATE, name="Mate no corredor")

    assert r.status_code == 200, r.text
    salvo = r.json()
    assert salvo["name"] == "Mate no corredor" and salvo["puzzle_id"]
    assert salvo["intro_comment"] == "Mate em um."
    assert salvo["tree"] == ARVORE_MATE and "[%cal Ga1a8]" in salvo["pgn"]
    resumo = client.get(f"/api/studies/{estudo['id']}").json()
    assert resumo["exercise_count"] == 1 and resumo["in_queue"] == 1
    fila = client.get("/api/queue", params={"study_id": estudo["id"]}).json()
    assert [item["id"] for item in fila["items"]] == [salvo["puzzle_id"]]


def test_salvar_arvore_com_lance_ilegal_422(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE)
    torta = {"fen": FEN_MATE, "orientation": "white", "intro": "", "root": {"shapes": [], "children": [
        {"id": "n1", "uci": "a1a4", "san": "Ra4", "comment": "", "shapes": [], "nags": [], "children": [
            {"id": "n2", "uci": "h1h8", "san": "??", "comment": "", "shapes": [], "nags": [], "children": []},
        ]},
    ]}}

    r = salvar_capitulo(client, estudo["id"], capitulo["id"], torta)

    assert r.status_code == 422
    assert any("lance ilegal" in erro for erro in r.json()["detail"])
    # nada foi gravado: o capítulo continua com a árvore vazia
    atual = client.get(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}").json()
    assert atual["tree"]["root"]["children"] == []


def test_mudar_a_posicao_inicial_para_a_de_outro_capitulo_422(client):
    estudo = criar_estudo(client)
    um = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE, mode="gamebook")
    salvar_capitulo(client, estudo["id"], um["id"], ARVORE_MATE, name="Um")
    dois = criar_capitulo(client, estudo["id"], name="Dois", fen=FEN_PEAO, mode="gamebook")
    salvo = salvar_capitulo(client, estudo["id"], dois["id"], ARVORE_PEAO, name="Dois").json()
    puzzle_de_dois = salvo["puzzle_id"]
    with client.app.state.session_factory() as db:
        db.add(Review(puzzle_id=puzzle_de_dois, reviewed_at=utcnow(), result="ok",
                      ease=2.5, interval_days=1, due_at=utcnow(), lapses=0))
        db.commit()

    r = salvar_capitulo(client, estudo["id"], dois["id"], ARVORE_MATE, name="Dois")

    assert r.status_code == 422, r.text
    assert r.json()["detail"] == ["posição inicial já usada por outro capítulo"]
    # a edição foi recusada inteira: o capítulo continua com a árvore e o exercício dele
    atual = client.get(f"/api/studies/{estudo['id']}/chapters/{dois['id']}").json()
    assert atual["puzzle_id"] == puzzle_de_dois and atual["tree"] == ARVORE_PEAO
    with client.app.state.session_factory() as db:
        assert db.get(Puzzle, puzzle_de_dois).fen_start == FEN_PEAO
        assert db.scalar(select(func.count(Review.id))) == 1


def test_salvar_com_fen_que_nao_e_texto_422(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE)

    r = salvar_capitulo(client, estudo["id"], capitulo["id"], {**ARVORE_MATE, "fen": 5})

    assert r.status_code == 422, r.text
    assert any("FEN inválida" in erro for erro in r.json()["detail"])


def test_salvar_com_modo_ou_orientacao_invalidos_422(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE)

    modo = salvar_capitulo(client, estudo["id"], capitulo["id"], ARVORE_MATE, mode="livro")
    orientacao = salvar_capitulo(client, estudo["id"], capitulo["id"], ARVORE_MATE, orientation="cima")

    assert modo.status_code == 422 and modo.json()["detail"] == ["modo inválido"]
    assert orientacao.status_code == 422
    assert orientacao.json()["detail"] == ["orientação inválida"]


def test_salvar_sem_a_arvore_422(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE)

    r = client.put(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}",
                   json={"name": "Um", "mode": "read", "orientation": "white"})

    assert r.status_code == 422, r.text


def test_salvar_arvore_sem_root_422_e_nao_mexe_no_capitulo(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE, mode="gamebook")
    antes = salvar_capitulo(client, estudo["id"], capitulo["id"], ARVORE_MATE, name="Um").json()

    r = salvar_capitulo(client, estudo["id"], capitulo["id"], {}, name="Outro")

    assert r.status_code == 422, r.text
    assert any('"root"' in erro for erro in r.json()["detail"])
    # árvore vazia não vira capítulo vazio: nada do que estava lá foi tocado
    atual = client.get(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}").json()
    assert atual["tree"] == ARVORE_MATE and atual["intro_comment"] == "Mate em um."
    assert atual["name"] == "Um" and atual["puzzle_id"] == antes["puzzle_id"]
    with client.app.state.session_factory() as db:
        assert db.get(Puzzle, antes["puzzle_id"]).in_queue is True


def test_salvar_capitulo_com_a_posicao_inicial_de_outro_422(client):
    estudo = criar_estudo(client)
    um = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE, mode="gamebook")
    salvar_capitulo(client, estudo["id"], um["id"], ARVORE_MATE, name="Um")
    dois = criar_capitulo(client, estudo["id"], name="Dois", fen=FEN_MATE, mode="gamebook")

    r = salvar_capitulo(client, estudo["id"], dois["id"], ARVORE_MATE, name="Dois")

    assert r.status_code == 422, r.text
    assert r.json()["detail"] == [
        "posição inicial já usada por outro capítulo; use outra posição inicial ou o modo leitura"
    ]
    # o capítulo não foi salvo pela metade: continua sem lances e sem exercício
    atual = client.get(f"/api/studies/{estudo['id']}/chapters/{dois['id']}").json()
    assert atual["tree"]["root"]["children"] == [] and atual["puzzle_id"] is None

    # em leitura não há exercício, e a mesma posição inicial passa
    leitura = salvar_capitulo(client, estudo["id"], dois["id"], ARVORE_MATE, name="Dois", mode="read")

    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["puzzle_id"] is None and leitura.json()["tree"] == ARVORE_MATE


def test_atualizar_o_estudo_sem_campo_algum_nao_mexe_no_updated_at(client):
    estudo = criar_estudo(client, "Antigo", "alguém")

    r = client.put(f"/api/studies/{estudo['id']}", json={})

    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] == estudo["updated_at"]
    assert r.json()["title"] == "Antigo" and r.json()["author"] == "alguém"


def test_duplicar_o_capitulo(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE, mode="gamebook")
    salvar_capitulo(client, estudo["id"], capitulo["id"], ARVORE_MATE)
    criar_capitulo(client, estudo["id"], name="Dois", fen=FEN_PEAO)

    r = client.post(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}/duplicate")

    assert r.status_code == 201, r.text
    copia = r.json()
    assert copia["name"] == "Um (cópia)" and copia["order"] == 2
    # a cópia teria a mesma posição inicial: entra como leitura, sem exercício
    assert copia["mode"] == "read" and copia["puzzle_id"] is None
    assert copia["tree"] == ARVORE_MATE
    ordem = [(c["name"], c["order"]) for c in client.get(f"/api/studies/{estudo['id']}").json()["chapters"]]
    assert ordem == [("Um", 1), ("Um (cópia)", 2), ("Dois", 3)]


def test_apagar_o_capitulo_tira_o_exercicio_da_fila(client):
    estudo = criar_estudo(client)
    capitulo = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE, mode="gamebook")
    salvar_capitulo(client, estudo["id"], capitulo["id"], ARVORE_MATE)
    outro = criar_capitulo(client, estudo["id"], name="Dois", fen=FEN_PEAO)

    assert client.delete(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}").status_code == 204

    resumo = client.get(f"/api/studies/{estudo['id']}").json()
    assert [(c["id"], c["order"]) for c in resumo["chapters"]] == [(outro["id"], 1)]
    assert resumo["exercise_count"] == 0 and resumo["in_queue"] == 0
    assert client.get("/api/dashboard").json()["by_source"]["study"]["in_queue"] == 0


def test_reordenar_e_renomear_o_estudo(client):
    estudo = criar_estudo(client, "Antigo", "alguém")
    ids = [criar_capitulo(client, estudo["id"], name=nome)["id"] for nome in ("Um", "Dois", "Três")]

    r = client.put(f"/api/studies/{estudo['id']}",
                   json={"title": "Novo", "author": "outro", "chapter_order": [ids[2], ids[0], ids[1]]})

    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Novo" and r.json()["author"] == "outro"
    capitulos = client.get(f"/api/studies/{estudo['id']}").json()["chapters"]
    assert [c["id"] for c in capitulos] == [ids[2], ids[0], ids[1]]
    assert [c["order"] for c in capitulos] == [1, 2, 3]


def test_ordem_incompleta_400(client):
    estudo = criar_estudo(client)
    ids = [criar_capitulo(client, estudo["id"], name=nome)["id"] for nome in ("Um", "Dois")]

    r = client.put(f"/api/studies/{estudo['id']}", json={"chapter_order": [ids[0]]})

    assert r.status_code == 400 and "capítulo" in r.json()["detail"]
    assert [c["id"] for c in client.get(f"/api/studies/{estudo['id']}").json()["chapters"]] == ids


def test_capitulo_de_outro_estudo_404(client):
    estudo = criar_estudo(client)
    outro = criar_estudo(client, "Outro")
    capitulo = criar_capitulo(client, outro["id"], name="Um")

    assert client.get(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}").status_code == 404
    assert client.delete(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}").status_code == 404
    assert client.get(f"/api/studies/{estudo['id']}/chapters/nada/pgn").status_code == 404


# --- exportação e round trip ---------------------------------------------


def test_exportar_o_pgn_do_estudo_e_do_capitulo(client):
    estudo = criar_estudo(client, "Táticas do Basso", "professor")
    capitulo = criar_capitulo(client, estudo["id"], name="Mate no corredor", fen=FEN_MATE, mode="gamebook")
    salvar_capitulo(client, estudo["id"], capitulo["id"], ARVORE_MATE, name="Mate no corredor")

    do_estudo = client.get(f"/api/studies/{estudo['id']}/pgn")
    do_capitulo = client.get(f"/api/studies/{estudo['id']}/chapters/{capitulo['id']}/pgn")

    assert do_estudo.status_code == 200
    assert do_estudo.headers["content-type"] == "text/plain; charset=utf-8"
    assert do_estudo.headers["content-disposition"] == 'attachment; filename="taticas-do-basso.pgn"'
    assert '[StudyName "Táticas do Basso"]' in do_estudo.text
    assert '[ChapterMode "gamebook"]' in do_estudo.text and "Ra8#" in do_estudo.text
    assert do_capitulo.headers["content-disposition"] == 'attachment; filename="mate-no-corredor.pgn"'
    assert do_capitulo.text.strip() == do_estudo.text.strip()


def test_round_trip_do_estudo_local(client):
    """Exportar um estudo feito aqui e importá-lo de volta dá as mesmas árvores."""
    estudo = criar_estudo(client, "Táticas do Basso", "professor")
    um = criar_capitulo(client, estudo["id"], name="Um", fen=FEN_MATE, mode="gamebook")
    salvar_capitulo(client, estudo["id"], um["id"], ARVORE_MATE, name="Um")
    dois = criar_capitulo(client, estudo["id"], name="Dois", fen=FEN_PEAO)
    salvar_capitulo(client, estudo["id"], dois["id"], ARVORE_PEAO, name="Dois", mode="read")

    importar(client, {"pgn": client.get(f"/api/studies/{estudo['id']}/pgn").text})

    estudos = client.get("/api/studies").json()
    assert len(estudos) == 2
    copia = next(e for e in estudos if e["id"] != estudo["id"])
    assert copia["title"] == "Táticas do Basso" and copia["author"] == "professor"
    assert arvores(client, copia["id"]) == arvores(client, estudo["id"])


def test_round_trip_do_estudo_importado(client):
    """O estudo real, exportado e reimportado, dá as mesmas árvores."""
    importar(client)
    original = client.get("/api/studies").json()[0]

    importar(client, {"pgn": client.get(f"/api/studies/{original['id']}/pgn").text})

    estudos = client.get("/api/studies").json()
    assert len(estudos) == 2
    copia = next(e for e in estudos if e["id"] != original["id"])
    assert copia["chapter_count"] == 27
    assert arvores(client, copia["id"]) == arvores(client, original["id"])


def test_capitulo_importado_antes_do_editor_ganha_a_arvore_ao_abrir(client):
    from chess_trainer.core.models import StudyChapter

    importar(client)
    estudo = client.get("/api/studies").json()[0]
    cid = client.get(f"/api/studies/{estudo['id']}").json()["chapters"][0]["id"]
    with client.app.state.session_factory() as db:
        db.get(StudyChapter, cid).tree_json = ""
        db.commit()

    detalhe = client.get(f"/api/studies/{estudo['id']}/chapters/{cid}").json()

    assert detalhe["tree"]["root"]["children"]
    with client.app.state.session_factory() as db:
        assert db.get(StudyChapter, cid).tree_json
