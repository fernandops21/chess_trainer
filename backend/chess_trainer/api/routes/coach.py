"""Rotas do treinador com IA (spec §9)."""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.routes.system import _engine_available
from chess_trainer.api.schemas import CoachExplainIn, CoachExplanationOut, CoachStatusOut
from chess_trainer.coach.costs import MODELO_CHECAGEM
from chess_trainer.coach.explain import OpcoesExplicacao, explicar, gravar
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.coach.observability import tracer_de
from chess_trainer.coach.tools import contexto_do_exercicio
from chess_trainer.config import load_settings
from chess_trainer.core.models import CoachExplanation, Puzzle, Review, utcnow
from chess_trainer.core.stats import theme_stats

router = APIRouter(prefix="/api/coach")

STATUS_POR_CODIGO = {"engine_indisponivel": 503}


def _blocos(row: CoachExplanation) -> dict:
    """Os blocos da resposta guardada. Explicação gravada antes deles (ou linha
    de banco migrado) vem vazia: o cartão cai no texto corrido."""
    try:
        est = json.loads(row.structured_json or "{}")
    except ValueError:
        est = {}
    if not isinstance(est, dict):
        est = {}
    treinar = est.get("treinar")
    return {
        "na_partida": est.get("na_partida") or None,
        "por_que": est.get("por_que") or None,
        "padrao": est.get("padrao") or None,
        "treinar": [str(t) for t in treinar] if isinstance(treinar, list) else [],
    }


def _out(row: CoachExplanation, trace_url: str | None) -> CoachExplanationOut:
    return CoachExplanationOut(
        id=row.id, puzzle_id=row.puzzle_id, created_at=row.created_at, model=row.model, prompt_version=row.prompt_version,
        text=row.text, **_blocos(row), lines=json.loads(row.lines_json), citations=json.loads(row.citations_json),
        verification=json.loads(row.verification_json), status=row.status, repaired=row.repaired, cost_usd=row.cost_usd,
        tokens={"input": row.input_tokens, "output": row.output_tokens, "cache_read": row.cache_read_tokens, "cache_write": row.cache_write_tokens},
        duration_ms=row.duration_ms, trace_url=trace_url,
    )


@router.get("/status", response_model=CoachStatusOut)
def coach_status(request: Request, db: Session = Depends(get_db)):
    s = load_settings(db)
    idx = request.app.state.coach_index.status(db)
    return CoachStatusOut(configured=bool(s.anthropic_api_key), model=s.coach_model, modelo_checagem=MODELO_CHECAGEM,
                          effort=s.coach_effort,
                          langfuse_configured=bool(s.langfuse_host and s.langfuse_public_key and s.langfuse_secret_key), **idx)


@router.post("/explain", response_model=CoachExplanationOut)
def coach_explain(body: CoachExplainIn, request: Request, db: Session = Depends(get_db)):
    app = request.app
    settings = load_settings(db)
    llm = app.state.coach_llm_factory(settings)
    if llm is None:
        raise HTTPException(409, "o treinador não está configurado: informe a chave da API em Configurações")
    # o segundo modelo, da checagem de afirmações, sai da mesma chave (nos testes, um FakeLlm)
    llm_checagem = app.state.coach_checagem_factory(settings)
    puzzle = db.get(Puzzle, body.puzzle_id)
    if puzzle is None:
        raise HTTPException(404, "puzzle não encontrado")
    # confere a revisão antes de gastar uma chamada ao modelo: a chave estrangeira
    # só reclamaria no `gravar`, depois da explicação inteira já ter rodado
    if body.review_id is not None and db.get(Review, body.review_id) is None:
        raise HTTPException(404, "revisão não encontrada")
    # o verificador precisa da engine para conferir as linhas: sem Stockfish a explicação
    # inteira sairia "não verificada" depois de gastar a chamada ao modelo
    disponivel, _ = _engine_available(request, settings)
    if not disponivel:
        raise HTTPException(503, "a engine (Stockfish) não está disponível; configure o caminho em Configurações")
    if not app.state.coach_lock.acquire(blocking=False):
        raise HTTPException(409, "já há uma explicação em andamento; espere ela terminar")
    try:
        contexto = contexto_do_exercicio(db, puzzle)
        # "mesma abertura" compara com o caminho dos trechos, que conta do início da partida:
        # a janela em volta do erro não casaria com nada
        caminho = contexto.abertura or None
        index = app.state.coach_index
        tracer = tracer_de(settings, app.state.coach_tracers)
        resultado = explicar(
            contexto=contexto, llm=llm, analisar=app.state.analyzer.analyse,
            estatisticas=lambda dias: theme_stats(db, utcnow() - timedelta(days=dias)),
            buscar=lambda consulta, k: index.buscar(db, consulta, k, caminho_san=caminho),
            opcoes=OpcoesExplicacao(effort=settings.coach_effort), tracer=tracer, llm_checagem=llm_checagem,
        )
    except ErroDoTreinador as exc:
        raise HTTPException(STATUS_POR_CODIGO.get(exc.codigo, 502), exc.mensagem) from exc
    finally:
        app.state.coach_lock.release()
    row = gravar(db, resultado, body.review_id)
    return _out(row, tracer.url(row.trace_id))


@router.get("/explanations/{puzzle_id}", response_model=CoachExplanationOut)
def coach_explanation(puzzle_id: str, request: Request, db: Session = Depends(get_db)):
    row = db.scalar(select(CoachExplanation).where(CoachExplanation.puzzle_id == puzzle_id)
                    .order_by(CoachExplanation.created_at.desc()))
    if row is None:
        raise HTTPException(404, "sem explicação para este exercício")
    tracer = tracer_de(load_settings(db), request.app.state.coach_tracers)
    return _out(row, tracer.url(row.trace_id))


@router.post("/reindex", status_code=202)
def coach_reindex(request: Request):
    app = request.app

    def job(progress):
        db = app.state.session_factory()
        try:
            app.state.coach_index.recriar(db, progress, should_stop=app.state.jobs.should_stop)
        finally:
            db.close()

    if not app.state.jobs.submit("coach_reindex", job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": "coach_reindex"}
