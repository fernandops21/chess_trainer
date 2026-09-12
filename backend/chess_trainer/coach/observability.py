"""Rastreio das etapas do treinador (spec §8.3). `NoopTracer` quando o LangFuse
não está configurado; `LangfuseTracer` entra na tarefa seguinte."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Protocol

from chess_trainer.coach.costs import Uso


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
