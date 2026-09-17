"""Golpes: status, tarefa de preparo (e, nas tarefas seguintes, irmãos, imagem e rotulagem)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import GolpesStatusOut
from chess_trainer.config import get_setting, load_settings
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.service import NOME_TAREFA, preparar
from chess_trainer.core.models import LichessPuzzle

router = APIRouter(prefix="/api/golpes")


def golpes_ligado(db: Session = Depends(get_db)) -> None:
    if not load_settings(db).golpes_enabled:
        raise HTTPException(404, "golpes desligados em Configurações")


@router.get("/status", response_model=GolpesStatusOut)
def golpes_status(request: Request, db: Session = Depends(get_db)):
    s = load_settings(db)
    # mesma fonte que `tactics_status` usa para o total: cache gravado na importação,
    # sem `COUNT(*)` no milhão de linhas do Lichess a cada pedido
    total = get_setting(db, "lichess_count")
    if total is None:
        total = db.scalar(select(func.count()).select_from(LichessPuzzle)) or 0
    return GolpesStatusOut(enabled=s.golpes_enabled, versao=VERSAO_ASSINATURA,
                           assinados=int(get_setting(db, "golpes_assinados", 0) or 0), total=int(total),
                           cobertura=get_setting(db, "golpes_cobertura", None),
                           rotulagem=bool(getattr(request.app.state, "rotulagem_enabled", False)))


@router.post("/preparar", status_code=202, dependencies=[Depends(golpes_ligado)])
def golpes_preparar(request: Request):
    app = request.app

    def job(progress):
        db = app.state.session_factory()
        try:
            preparar(db, progress, should_stop=app.state.jobs.should_stop)
        finally:
            db.close()

    if not app.state.jobs.submit(NOME_TAREFA, job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": NOME_TAREFA}
