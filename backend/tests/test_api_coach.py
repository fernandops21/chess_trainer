import json

import chess
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.coach.tools import contexto_do_exercicio
from chess_trainer.core.models import CoachExplanation, Puzzle
from tests.fakes import EmbeddingsFalso, FakeEngine, FakeLlm, first_legal_default
from tests.test_api_system import chesscom_factory
from tests.test_api_training import engine_factory

TEXTO = " ".join(["explicação"] * 70)
NA_PARTIDA = "Na partida o lance natural devolveu a vantagem."
FINAL = {"na_partida": NA_PARTIDA, "por_que": TEXTO, "linhas": [], "citacoes": [],
         "padrao": "peça pendurada", "treinar": ["revisar mates simples", "conferir capturas antes de mover"]}


def montar(llm, checador=None):
    """`checador`: o modelo da checagem de afirmações; por padrão um FakeLlm novo por pedido,
    que não lista afirmação nenhuma (a rota tem de passar por ele sem rede)."""
    def checagem(s):
        if not s.anthropic_api_key:
            return None
        return checador if checador is not None else FakeLlm([[("final", {"afirmacoes": []})]])

    app = create_app(db_path=":memory:", engine_factory=engine_factory, chesscom_factory=chesscom_factory,
                     analysis_engine_factory=lambda: FakeEngine(default=first_legal_default(0)),
                     embeddings_factory=EmbeddingsFalso, coach_llm_factory=lambda s: llm if s.anthropic_api_key else None,
                     coach_checagem_factory=checagem)
    client = TestClient(app)
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import"); app.state.jobs.wait()
    client.post("/api/analyze"); app.state.jobs.wait()
    puzzle_id = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]["id"]
    return app, client, puzzle_id


def test_status_e_409_sem_chave():
    app, client, pid = montar(FakeLlm([]))
    st = client.get("/api/coach/status").json()
    assert st["configured"] is False and st["model"] == "claude-opus-5" and st["index_chunks"] == 0 and st["embeddings_ready"] is False
    assert st["modelo_checagem"] == "claude-sonnet-5"
    assert st["vector_backend"] in ("sqlite-vec", "numpy") and st["langfuse_configured"] is False
    r = client.post("/api/coach/explain", json={"puzzle_id": pid})
    assert r.status_code == 409 and "Configurações" in r.json()["detail"]


def test_explain_feliz_reabrir_e_404():
    llm = FakeLlm([[("final", FINAL)]])
    app, client, pid = montar(llm)
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x", "coach_effort": "low"})
    assert client.get("/api/coach/status").json()["configured"] is True
    r = client.post("/api/coach/explain", json={"puzzle_id": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["text"] == NA_PARTIDA + "\n\n" + TEXTO and body["verification"]["ok"] and body["tokens"]["input"] == 1000
    # os blocos vão junto: o cartão lê deles, não do texto corrido
    assert body["na_partida"] == NA_PARTIDA and body["por_que"] == TEXTO and body["padrao"] == "peça pendurada"
    assert body["treinar"] == ["revisar mates simples", "conferir capturas antes de mover"]
    assert body["citations"] == [] and body["trace_url"] is None and body["model"] == "fake" and llm.prompts[0]["effort"] == "low"
    assert client.get(f"/api/coach/explanations/{pid}").json()["id"] == body["id"]
    assert client.get("/api/coach/explanations/nao-existe").status_code == 404
    assert client.post("/api/coach/explain", json={"puzzle_id": "nao-existe"}).status_code == 404


def test_explain_passa_pela_checagem_de_afirmacoes():
    """A rota entrega o segundo modelo ao pipeline: uma afirmação falsa dele vira erro da explicação."""
    llm = FakeLlm([[("final", FINAL)], [("final", FINAL)]])
    falsa = {"tipo": "ataca", "trecho": "a dama de a1 ataca h8", "peca": "a1", "alvo": "h8", "lance": None, "lado": None, "tipo_peca": None, "casas": []}
    checador = FakeLlm([[("final", {"afirmacoes": [falsa]})], [("final", {"afirmacoes": [falsa]})]])
    app, client, pid = montar(llm, checador)
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    r = client.post("/api/coach/explain", json={"puzzle_id": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "errors" and [i["tipo"] for i in body["verification"]["issues"]] == ["afirmacao_falsa"]
    assert "a dama de a1 ataca h8" in body["verification"]["issues"][0]["detalhe"]
    # a correção foi tentada (o checador foi chamado duas vezes) e o texto da explicação foi ao checador
    assert len(checador.prompts) == 2 and TEXTO in checador.prompts[0]["user"] and "afirmacao_falsa" in llm.prompts[1]["user"]


def test_review_inexistente_da_404_antes_de_chamar_o_modelo():
    llm = FakeLlm([])  # sem roteiro: qualquer chamada ao modelo quebraria o teste
    app, client, pid = montar(llm)
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    r = client.post("/api/coach/explain", json={"puzzle_id": pid, "review_id": "nao-existe"})
    assert r.status_code == 404 and r.json()["detail"] == "revisão não encontrada"
    assert llm.prompts == []


def test_explain_guarda_a_revisao_informada():
    app, client, pid = montar(FakeLlm([[("final", FINAL)]]))
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    review_id = client.post("/api/reviews", json={"puzzle_id": pid, "correct": True}).json()["id"]
    r = client.post("/api/coach/explain", json={"puzzle_id": pid, "review_id": review_id})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/coach/explanations/{pid}").json()["id"] == r.json()["id"]
    with app.state.session_factory() as db:
        assert db.get(CoachExplanation, r.json()["id"]).review_id == review_id


def test_erros_do_treinador_viram_502_ou_503():
    class Quebrado:
        model = "fake"

        def __init__(self, codigo):
            self.codigo = codigo

        def run_agent(self, **kw):
            raise ErroDoTreinador(self.codigo, "mensagem legível")

    for codigo, status in (("limite_de_uso", 502), ("engine_indisponivel", 503), ("recusa", 502)):
        app, client, pid = montar(Quebrado(codigo))
        client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
        r = client.post("/api/coach/explain", json={"puzzle_id": pid})
        assert r.status_code == status and r.json()["detail"] == "mensagem legível", codigo
        # o erro não pode deixar o lock preso: a próxima tentativa tem de passar
        assert app.state.coach_lock.acquire(blocking=False), codigo
        app.state.coach_lock.release()


def test_busca_usa_a_abertura_da_partida():
    """A busca por "mesma abertura" compara com o caminho dos trechos, que conta do início
    da partida: quem vai no `caminho_san` é a abertura, não a janela em volta do erro."""
    app, client, pid = montar(FakeLlm([[("final", FINAL)]]))
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    chamadas = []
    original = app.state.coach_index.buscar

    def espiao(db, consulta, k, caminho_san=None):
        chamadas.append(caminho_san)
        return original(db, consulta, k, caminho_san=caminho_san)

    app.state.coach_index.buscar = espiao
    assert client.post("/api/coach/explain", json={"puzzle_id": pid}).status_code == 200
    with app.state.session_factory() as db:
        ctx = contexto_do_exercicio(db, db.get(Puzzle, pid))
    assert chamadas and chamadas[0] == ctx.abertura
    assert len(ctx.abertura.split()) == 6 and ctx.abertura.startswith("1.")
    assert chamadas[0] != ctx.partida["lances_em_volta"]


def test_sem_engine_da_503_e_nao_chama_o_modelo():
    """O verificador não roda sem Stockfish: melhor recusar antes de gastar a chamada paga."""
    llm = FakeLlm([])  # sem roteiro: qualquer chamada ao modelo quebraria o teste
    app, client, pid = montar(llm)
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    app.state.engine_probe = lambda s: (False, None)
    r = client.post("/api/coach/explain", json={"puzzle_id": pid})
    assert r.status_code == 503 and "Stockfish" in r.json()["detail"]
    assert llm.prompts == []
    assert app.state.coach_lock.acquire(blocking=False)  # nem chegou a pegar a trava
    app.state.coach_lock.release()


def test_uma_explicacao_por_vez():
    app, client, pid = montar(FakeLlm([[("final", FINAL)]]))
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    assert app.state.coach_lock.acquire(blocking=False)
    try:
        r = client.post("/api/coach/explain", json={"puzzle_id": pid})
        assert r.status_code == 409 and "andamento" in r.json()["detail"]
    finally:
        app.state.coach_lock.release()


def test_reindex_via_job():
    app, client, pid = montar(FakeLlm([]))
    r = client.post("/api/coach/reindex")
    assert r.status_code == 202 and r.json() == {"queued": True, "job": "coach_reindex"}
    app.state.jobs.wait()
    assert app.state.jobs.snapshot()["state"] == "idle"
    assert client.get("/api/coach/status").json()["embeddings_ready"] is True


def test_cada_linha_volta_com_a_fen_de_onde_parte():
    """`fen_inicio`: é por ele que o cartão resolve os lances numerados da prosa pela linha
    certa, em vez de jogar todos a partir da posição do exercício."""
    app, client, pid = montar(FakeLlm([[("final", FINAL)]]))
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    assert client.post("/api/coach/explain", json={"puzzle_id": pid}).status_code == 200
    gravadas = [{"inicio": onde, "lances": [], "avaliacao_cp": 0, "mate_em": None}
                for onde in ("inicial", "erro", "ameaca")]
    with app.state.session_factory() as db:
        row = db.query(CoachExplanation).filter_by(puzzle_id=pid).one()
        row.lines_json = json.dumps(gravadas)
        db.commit()
        ctx = contexto_do_exercicio(db, db.get(Puzzle, pid))
    assert ctx.fen_erro and ctx.fen_erro != ctx.fen_inicial, "o exercício do fixture tem posição do erro"
    linhas = client.get(f"/api/coach/explanations/{pid}").json()["lines"]
    assert linhas[0]["fen_inicio"] == chess.Board(ctx.fen_inicial).fen()
    assert linhas[1]["fen_inicio"] == chess.Board(ctx.fen_erro).fen()
    # a linha de ameaça parte do lance nulo: as mesmas peças, o outro lado a mover
    ameaca, inicial = linhas[2]["fen_inicio"].split(), linhas[0]["fen_inicio"].split()
    assert ameaca[0] == inicial[0] and ameaca[1] != inicial[1]


def test_explicacao_antiga_sem_blocos_volta_so_com_o_texto():
    """Linha gravada antes dos blocos: `structured_json` vazio, e o cartão cai no `text`."""
    app, client, pid = montar(FakeLlm([[("final", FINAL)]]))
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    assert client.post("/api/coach/explain", json={"puzzle_id": pid}).status_code == 200
    with app.state.session_factory() as db:
        row = db.query(CoachExplanation).filter_by(puzzle_id=pid).one()
        row.structured_json = "{}"
        db.commit()
    body = client.get(f"/api/coach/explanations/{pid}").json()
    assert body["na_partida"] is None and body["por_que"] is None and body["padrao"] is None
    assert body["treinar"] == [] and body["text"].startswith(NA_PARTIDA)
