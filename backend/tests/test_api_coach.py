import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.config import set_setting
from tests.fakes import EmbeddingsFalso, FakeEngine, FakeLlm, first_legal_default
from tests.test_api_system import chesscom_factory
from tests.test_api_training import engine_factory

TEXTO = " ".join(["explicação"] * 70)
FINAL = {"texto": TEXTO, "linhas": [], "citacoes": [], "padrao": None, "treinar": ["revisar mates simples"]}


def montar(llm):
    app = create_app(db_path=":memory:", engine_factory=engine_factory, chesscom_factory=chesscom_factory,
                     analysis_engine_factory=lambda: FakeEngine(default=first_legal_default(0)),
                     embeddings_factory=EmbeddingsFalso, coach_llm_factory=lambda s: llm if s.anthropic_api_key else None)
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
    assert body["status"] == "ok" and body["text"] == TEXTO and body["verification"]["ok"] and body["tokens"]["input"] == 1000
    assert body["citations"] == [] and body["trace_url"] is None and body["model"] == "fake" and llm.prompts[0]["effort"] == "low"
    assert client.get(f"/api/coach/explanations/{pid}").json()["id"] == body["id"]
    assert client.get("/api/coach/explanations/nao-existe").status_code == 404
    assert client.post("/api/coach/explain", json={"puzzle_id": "nao-existe"}).status_code == 404


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
