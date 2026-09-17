"""Golpes: status, tarefa de preparo, busca de irmãos (e, nas tarefas seguintes, imagem e rotulagem)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import GolpesStatusOut, IrmaoOut, IrmaosOut
from chess_trainer.config import get_setting, load_settings
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.imagem import svg_do_golpe
from chess_trainer.core.golpes.service import NOME_TAREFA, assinatura_de, irmaos, preparar
from chess_trainer.core.models import LichessPuzzle, Puzzle, utcnow
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.service import _seen_ids

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


@router.get("/{origem}/{id}/irmaos", response_model=IrmaosOut, dependencies=[Depends(golpes_ligado)])
def golpes_irmaos(origem: str, id: str, k: int | None = None, db: Session = Depends(get_db)):
    achado = assinatura_de(db, origem, id)
    if achado is None:
        raise HTTPException(404, "exercício sem assinatura de golpe")
    a, _fen, _lances = achado
    s = load_settings(db)
    n = max(1, min(10, s.golpes_bloco if k is None else k))
    excluir = _seen_ids(db, utcnow(), [id] if origem == "lichess" else [])
    excluir |= set(db.scalars(select(Puzzle.external_id).where(Puzzle.external_id.is_not(None))))
    lo, hi = s.tactics_rating - s.tactics_window, s.tactics_rating + s.tactics_window
    itens = []
    for irmao in irmaos(db, a, rating_lo=lo, rating_hi=hi, excluir=excluir, k=n):
        try:
            itens.append(IrmaoOut(tier=irmao.tier, tactic=asdict(to_tactic(irmao.row))))
        except ValueError:
            continue
    return IrmaosOut(assinatura=a.destinos(), itens=itens)


@router.get("/{origem}/{id}/imagem.svg", dependencies=[Depends(golpes_ligado)])
def golpes_imagem(origem: str, id: str, db: Session = Depends(get_db)):
    achado = assinatura_de(db, origem, id)
    if achado is None:
        raise HTTPException(404, "exercício sem assinatura de golpe")
    _a, fen, lances = achado
    return Response(content=svg_do_golpe(fen, lances), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})
