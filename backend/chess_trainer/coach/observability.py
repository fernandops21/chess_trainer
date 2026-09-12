"""Rastreio das etapas do treinador (spec §8.3). Dois tracers atrás da mesma
interface: `LangfuseTracer` manda os spans e as gerações (modelo, tokens, custo)
para o LangFuse configurado em Configurações; `NoopTracer` engole tudo quando não
há host nem chaves. `tracer_de` escolhe um dos dois a cada pedido."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Protocol

from chess_trainer.coach.costs import Uso
from chess_trainer.config import AppSettings


class Tracer(Protocol):
    def span(self, nome: str, **meta) -> Iterator[None]: ...

    def geracao(self, nome: str, model: str, uso: Uso, custo: float, **meta) -> None: ...

    def trace_id(self) -> str | None: ...

    def url(self, trace_id: str | None) -> str | None: ...

    def flush(self) -> None: ...


class NoopTracer:
    @contextmanager
    def span(self, nome: str, **meta):
        yield

    def geracao(self, nome: str, model: str, uso: Uso, custo: float, **meta) -> None:
        pass

    def trace_id(self) -> str | None:
        return None

    def url(self, trace_id: str | None) -> str | None:
        return None

    def flush(self) -> None:
        pass


class LangfuseTracer:
    """Envia spans e gerações para o LangFuse (SDK v4, baseado em OpenTelemetry)."""

    def __init__(self, public_key: str, secret_key: str, host: str, client: Any = None):
        self.host = host.rstrip("/")
        if client is None:
            from langfuse import Langfuse

            client = Langfuse(public_key=public_key, secret_key=secret_key, host=self.host)
        self._lf = client

    @contextmanager
    def span(self, nome: str, **meta):
        with self._lf.start_as_current_observation(as_type="span", name=nome) as obs:
            if meta:
                obs.update(metadata=meta)
            yield

    def geracao(self, nome: str, model: str, uso: Uso, custo: float, **meta) -> None:
        with self._lf.start_as_current_observation(as_type="generation", name=nome) as gen:
            gen.update(model=model, usage_details=uso.to_dict(), cost_details={"total": custo}, metadata=meta)

    def trace_id(self) -> str | None:
        return self._lf.get_current_trace_id()

    def url(self, trace_id: str | None) -> str | None:
        return f"{self.host}/trace/{trace_id}" if trace_id else None

    def flush(self) -> None:
        self._lf.flush()


def tracer_de(settings: AppSettings, cache: dict | None = None,
              fabrica: Callable[[str, str, str], Tracer] | None = None) -> Tracer:
    """Devolve o tracer do LangFuse configurado em `settings`, ou `NoopTracer` sem
    host/chaves; reaproveita a instância no `cache` pela tupla (public_key, secret_key, host)."""
    pk, sk, host = settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host
    if not (pk and sk and host):
        return NoopTracer()
    chave = (pk, sk, host)
    if cache is not None and chave in cache:
        return cache[chave]
    tracer = (fabrica or LangfuseTracer)(pk, sk, host)
    if cache is not None:
        cache[chave] = tracer
    return tracer
