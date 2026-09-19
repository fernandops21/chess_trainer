"""Golpes: status, tarefa de preparo, busca de irmãos, imagem e voto (conjunto de ouro)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import (
    GolpesStatusOut, IrmaoOut, IrmaosOut, VotoConsultaOut, VotoIn, VotoOut, VotosResumoLinha,
)
from chess_trainer.config import get_setting, load_settings
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.imagem import svg_do_golpe
from chess_trainer.core.golpes.mates import NOME_PT, padroes_do_exercicio
from chess_trainer.core.golpes.service import NOME_TAREFA, assinatura_de, irmaos, preparar
from chess_trainer.core.golpes.votos import resumo, voto_de, votar
from chess_trainer.core.models import LichessPuzzle, Puzzle, utcnow
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.service import _seen_ids

router = APIRouter(prefix="/api/golpes")


def golpes_ligado(db: Session = Depends(get_db)) -> None:
    if not load_settings(db).golpes_enabled:
        raise HTTPException(404, "golpes desligados em Configurações")


@router.get("/status", response_model=GolpesStatusOut)
def golpes_status(db: Session = Depends(get_db)):
    s = load_settings(db)
    # mesma fonte que `tactics_status` usa para o total: cache gravado na importação,
    # sem `COUNT(*)` no milhão de linhas do Lichess a cada pedido
    total = get_setting(db, "lichess_count")
    if total is None:
        total = db.scalar(select(func.count()).select_from(LichessPuzzle)) or 0
    return GolpesStatusOut(enabled=s.golpes_enabled, versao=VERSAO_ASSINATURA,
                           assinados=int(get_setting(db, "golpes_assinados", 0) or 0), total=int(total),
                           cobertura=get_setting(db, "golpes_cobertura", None),
                           trechos=int(get_setting(db, "golpes_trechos", 0) or 0),
                           padroes=int(get_setting(db, "golpes_padroes", 0) or 0))


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
    a, fen, lances = achado
    s = load_settings(db)
    n = max(1, min(10, s.golpes_bloco if k is None else k))
    excluir = _seen_ids(db, utcnow(), [id] if origem == "lichess" else [])
    excluir |= set(db.scalars(select(Puzzle.external_id).where(Puzzle.external_id.is_not(None))))
    itens = []
    for irmao in irmaos(db, fen, lances, rating=s.tactics_rating, abaixo=s.golpes_faixa_abaixo,
                        acima=s.golpes_faixa_acima, excluir=excluir, k=n):
        try:
            itens.append(IrmaoOut(tier=irmao.tier, procedencia=asdict(irmao.procedencia), tactic=asdict(to_tactic(irmao.row))))
        except ValueError:
            continue
    mate = padroes_do_exercicio(fen, lances)
    # um mate pode ter mais de um padrão: "mate árabe + mate do corredor"
    padrao = None if mate is None else (" + ".join(NOME_PT[t] for t in mate[0] if t in NOME_PT) or None)
    return IrmaosOut(assinatura=a.destinos(), itens=itens, padrao=padrao)


@router.get("/{origem}/{id}/imagem.svg", dependencies=[Depends(golpes_ligado)])
def golpes_imagem(origem: str, id: str, db: Session = Depends(get_db)):
    achado = assinatura_de(db, origem, id)
    if achado is None:
        raise HTTPException(404, "exercício sem assinatura de golpe")
    _a, fen, lances = achado
    # exercício próprio: a solução pode mudar sob o mesmo id (extensão da linha, edição do
    # capítulo), então cachear por um dia serviria uma imagem velha; só o Lichess é imutável
    cache = "public, max-age=86400" if origem == "lichess" else "no-cache"
    return Response(content=svg_do_golpe(fen, lances), media_type="image/svg+xml",
                    headers={"Cache-Control": cache})


def _existe_ancora(db: Session, origem: str, id: str) -> bool:
    if origem == "own":
        return db.get(Puzzle, id) is not None
    return db.get(LichessPuzzle, id) is not None


@router.post("/voto", response_model=VotoOut, dependencies=[Depends(golpes_ligado)])
def golpes_votar(body: VotoIn, db: Session = Depends(get_db)):
    if not _existe_ancora(db, body.anchor_origem, body.anchor_id):
        raise HTTPException(404, "âncora não encontrada")
    if db.get(LichessPuzzle, body.candidate_id) is None:
        raise HTTPException(404, "candidato não encontrado")
    try:
        linha = votar(db, anchor_origem=body.anchor_origem, anchor_id=body.anchor_id,
                     candidate_id=body.candidate_id, tier=body.tier, label=body.label,
                     n_lances=body.n_lances, posicao=body.posicao, nivel=body.nivel, espelhado=body.espelhado)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return VotoOut(ok=True, label=linha.label)


@router.get("/voto", response_model=VotoConsultaOut, dependencies=[Depends(golpes_ligado)])
def golpes_voto(anchor_origem: str, anchor_id: str, candidate_id: str, db: Session = Depends(get_db)):
    return VotoConsultaOut(label=voto_de(db, anchor_origem=anchor_origem, anchor_id=anchor_id, candidate_id=candidate_id))


@router.get("/votos/resumo", response_model=list[VotosResumoLinha], dependencies=[Depends(golpes_ligado)])
def golpes_votos_resumo(db: Session = Depends(get_db)):
    return resumo(db)
