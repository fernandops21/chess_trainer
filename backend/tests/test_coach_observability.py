from contextlib import contextmanager
from types import SimpleNamespace

from chess_trainer.coach.costs import Uso
from chess_trainer.coach.observability import LangfuseTracer, NoopTracer, tracer_de
from chess_trainer.config import AppSettings


class LangfuseFalso:
    def __init__(self):
        self.obs = []
        self.flushed = False

    @contextmanager
    def start_as_current_observation(self, **kw):
        registro = {"kw": kw, "updates": []}
        self.obs.append(registro)
        yield SimpleNamespace(update=lambda **u: registro["updates"].append(u))

    def get_current_trace_id(self):
        return "abc123"

    def flush(self):
        self.flushed = True


def test_tracer_de_sem_configuracao_e_noop():
    assert isinstance(tracer_de(AppSettings()), NoopTracer)
    assert isinstance(tracer_de(AppSettings(langfuse_host="http://x", langfuse_public_key="pk")), NoopTracer)  # sem secret


def test_tracer_de_reaproveita_a_instancia():
    cache = {}
    s = AppSettings(langfuse_host="http://x", langfuse_public_key="pk", langfuse_secret_key="sk")
    a = tracer_de(s, cache, fabrica=lambda pk, sk, host: LangfuseTracer(pk, sk, host, client=LangfuseFalso()))
    b = tracer_de(s, cache, fabrica=lambda pk, sk, host: LangfuseTracer(pk, sk, host, client=LangfuseFalso()))
    assert a is b and isinstance(a, LangfuseTracer)


def test_langfuse_tracer_registra_spans_geracoes_e_url():
    lf = LangfuseFalso()
    t = LangfuseTracer("pk", "sk", "http://localhost:3000", client=lf)
    with t.span("coach.explain", puzzle_id="p1"):
        assert t.trace_id() == "abc123"
        t.geracao("llm", "claude-opus-5", Uso(10, 5, 3, 1), 0.01, chamadas=["analisar_posicao"])
    t.flush()
    assert lf.obs[0]["kw"]["name"] == "coach.explain" and lf.obs[0]["kw"]["as_type"] == "span"
    assert lf.obs[0]["updates"][0]["metadata"] == {"puzzle_id": "p1"}
    g = lf.obs[1]
    assert g["kw"]["as_type"] == "generation" and g["kw"]["name"] == "llm"
    u = g["updates"][-1]
    assert u["model"] == "claude-opus-5" and u["usage_details"]["input"] == 10 and u["cost_details"]["total"] == 0.01
    assert t.url("abc123") == "http://localhost:3000/trace/abc123" and lf.flushed
