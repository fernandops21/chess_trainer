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
def client(tmp_path):
    # banco em arquivo, não ":memory:": em memória todas as sessões dividem UMA conexão, e o
    # rollback do fim da requisição derrubava o lote que a tarefa em segundo plano ainda não
    # tinha gravado (falha intermitente de ~1 em 6). No app real cada sessão tem a sua conexão.
    app = create_app(db_path=str(tmp_path / "golpes.db"), engine_factory=lambda s: FakeEngine(default=first_legal_default(0)))
    with TestClient(app) as c:
        db = app.state.session_factory()
        for i in range(6):
            db.add(pastor(f"p{i}", 700 + 100 * i))
        db.commit(); db.close()
        yield c


def test_status_e_preparar(client):
    s = client.get("/api/golpes/status").json()
    assert s["enabled"] is True and s["versao"] == 2 and s["assinados"] == 0 and s["cobertura"] is None
    assert s["trechos"] == 0 and s["padroes"] == 0
    assert client.post("/api/golpes/preparar").status_code == 202
    client.app.state.jobs.wait()
    assert client.get("/api/status").json()["job"]["state"] == "idle"
    s = client.get("/api/golpes/status").json()
    assert s["assinados"] == 6 and s["cobertura"]["destinos"]["ge5"] == 6
    assert s["trechos"] > 0
    # nenhum puzzle do fixture tem o tema geral "mate" na tabela de junção: a varredura das
    # etiquetas próprias roda (mesmo clique) mas não acha nada para rotular
    assert s["padroes"] == 0


def test_desligado_da_404(client):
    assert client.put("/api/settings", json={"golpes_enabled": False}).status_code == 200
    assert client.post("/api/golpes/preparar").status_code == 404
    assert client.get("/api/golpes/status").json()["enabled"] is False


def test_settings_validam_o_bloco(client):
    assert client.put("/api/settings", json={"golpes_bloco": 2}).status_code == 422
    assert client.put("/api/settings", json={"golpes_bloco": 7}).status_code == 200
    assert client.get("/api/settings").json()["golpes_bloco"] == 7


def test_settings_validam_a_faixa_do_bloco(client):
    assert client.put("/api/settings", json={"golpes_faixa_abaixo": -1}).status_code == 422
    assert client.put("/api/settings", json={"golpes_faixa_abaixo": 1001}).status_code == 422
    assert client.put("/api/settings", json={"golpes_faixa_acima": -1}).status_code == 422
    assert client.put("/api/settings", json={"golpes_faixa_acima": 2001}).status_code == 422
    assert client.put("/api/settings", json={"golpes_faixa_abaixo": 50, "golpes_faixa_acima": 300}).status_code == 200
    s = client.get("/api/settings").json()
    assert s["golpes_faixa_abaixo"] == 50 and s["golpes_faixa_acima"] == 300


def test_irmaos_usa_a_faixa_configurada(client):
    """A rota lê `golpes_faixa_abaixo/acima` das configurações: faixa de largura zero em volta
    do rating escolhe exatamente o puzzle daquele rating, não o mais fácil da cascata."""
    client.post("/api/golpes/preparar"); client.app.state.jobs.wait()
    # a própria âncora (p0, 700) sai da busca; a faixa de largura zero em 800 aponta exatamente p1
    client.put("/api/settings", json={"tactics_rating": 800, "golpes_faixa_abaixo": 0, "golpes_faixa_acima": 0})
    r = client.get("/api/golpes/lichess/p0/irmaos?k=1").json()
    assert r["itens"][0]["tactic"]["rating"] == 800


def test_irmaos_de_um_puzzle_do_lichess(client):
    client.post("/api/golpes/preparar"); client.app.state.jobs.wait()
    client.put("/api/settings", json={"tactics_rating": 900, "tactics_window": 400})
    r = client.get("/api/golpes/lichess/p0/irmaos?k=3").json()
    assert r["assinatura"].startswith("Ke8 | Q") and len(r["itens"]) == 3
    assert all(i["tier"] == "inteira" for i in r["itens"]) and r["itens"][0]["tactic"]["id"] != "p0"
    assert r["itens"][0]["tactic"]["fen_start"] and r["itens"][0]["tactic"]["rating"] <= r["itens"][-1]["tactic"]["rating"]
    assert r["itens"][0]["procedencia"] == {"degrau": "inteira", "nivel": "destinos", "n": 1, "posicao": "inteira", "espelhado": False}
    assert client.get("/api/golpes/lichess/nao/irmaos").status_code == 404
    assert client.get("/api/golpes/own/nao/irmaos").status_code == 404
    # k=0 não é "não informado": é o pedido de um único item, não o padrão de golpes_bloco
    assert len(client.get("/api/golpes/lichess/p0/irmaos?k=0").json()["itens"]) == 1


def test_irmaos_traz_o_padrao_de_mate_da_ancora(client):
    """A resposta traz o nome em português do padrão de mate da âncora quando a solução dela
    termina num xeque-mate com padrão aprovado (spec golpes design §3.6); sem padrão (ou sem
    mate), o campo fica nulo."""
    db = client.app.state.session_factory()
    corredor = LichessPuzzle(
        id="corr1", fen="6k1/p4ppp/8/8/8/8/5PPP/4R1K1 b - - 0 1", moves="a7a6 e1e8", rating=800,
        rating_deviation=50, popularity=90, nb_plays=500, themes="backRankMate mateIn1", opening_tags="")
    db.add(corredor)
    db.commit()
    db.close()
    assert client.get("/api/golpes/lichess/corr1/irmaos").json()["padrao"] == "mate do corredor"
    # p0 é o mate do pastor: xeque-mate, mas sem nenhum dos três padrões aprovados
    assert client.get("/api/golpes/lichess/p0/irmaos").json()["padrao"] is None


def test_imagem_svg(client):
    client.post("/api/golpes/preparar"); client.app.state.jobs.wait()
    r = client.get("/api/golpes/lichess/p0/imagem.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and r.text.startswith("<svg")
    assert "max-age" in r.headers["cache-control"]
    assert client.get("/api/golpes/lichess/nao/imagem.svg").status_code == 404


def test_imagem_svg_de_exercicio_proprio_nao_tem_cache_longo(client):
    """Achado 6 da revisão: a solução de um exercício próprio pode mudar sob o mesmo id
    (extensão da linha, edição do capítulo) — cachear por um dia serviria uma imagem velha."""
    from chess_trainer.core.models import Puzzle

    db = client.app.state.session_factory()
    puzzle = Puzzle(
        kind="punish", fen_start="r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 5 5",
        side_to_move="white", solution='{"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}]}',
        end_reason="mate", theme="mateIn1", category="rapid", solver_moves=1, source="own",
    )
    db.add(puzzle); db.commit()
    pid = puzzle.id
    db.close()

    r = client.get(f"/api/golpes/own/{pid}/imagem.svg")
    assert r.status_code == 200 and r.text.startswith("<svg")
    assert r.headers["cache-control"] == "no-cache"


def voto_body(**over):
    body = {"anchor_origem": "lichess", "anchor_id": "p0", "candidate_id": "p1", "tier": "inteira", "label": "mesmo"}
    body.update(over)
    return body


def test_voto_grava_e_consulta(client):
    client.post("/api/golpes/preparar"); client.app.state.jobs.wait()
    assert client.get("/api/golpes/voto", params={"anchor_origem": "lichess", "anchor_id": "p0", "candidate_id": "p1"}).json() == {"label": None}
    r = client.post("/api/golpes/voto", json=voto_body(n_lances=1, posicao="inteira", nivel="destinos", espelhado=False))
    assert r.status_code == 200 and r.json() == {"ok": True, "label": "mesmo"}
    assert client.get("/api/golpes/voto", params={"anchor_origem": "lichess", "anchor_id": "p0", "candidate_id": "p1"}).json() == {"label": "mesmo"}


def test_votar_de_novo_atualiza_sem_duplicar(client):
    client.post(f"/api/golpes/voto", json=voto_body(label="nada"))
    r = client.post("/api/golpes/voto", json=voto_body(label="parecido"))
    assert r.status_code == 200 and r.json()["label"] == "parecido"
    assert client.get("/api/golpes/voto", params={"anchor_origem": "lichess", "anchor_id": "p0", "candidate_id": "p1"}).json()["label"] == "parecido"


def test_voto_rotulo_invalido_422(client):
    assert client.post("/api/golpes/voto", json=voto_body(label="talvez")).status_code == 422


def test_voto_ancora_ou_candidato_desconhecido_404(client):
    assert client.post("/api/golpes/voto", json=voto_body(anchor_id="nao-existe")).status_code == 404
    assert client.post("/api/golpes/voto", json=voto_body(candidate_id="nao-existe")).status_code == 404
    assert client.post("/api/golpes/voto", json=voto_body(anchor_origem="own", anchor_id="nao-existe")).status_code == 404


def test_voto_desligado_da_404(client):
    client.put("/api/settings", json={"golpes_enabled": False})
    assert client.post("/api/golpes/voto", json=voto_body()).status_code == 404
    assert client.get("/api/golpes/voto", params={"anchor_origem": "lichess", "anchor_id": "p0", "candidate_id": "p1"}).status_code == 404


def test_votos_resumo(client):
    client.post("/api/golpes/voto", json=voto_body(n_lances=1, posicao="inteira", nivel="destinos", espelhado=False))
    r = client.get("/api/golpes/votos/resumo")
    assert r.status_code == 200
    linhas = r.json()
    assert linhas == [{"tier": "inteira", "posicao": "inteira", "n_lances": 1, "nivel": "destinos",
                       "mesmo": 1, "parecido": 0, "nada": 0, "total": 1}]
