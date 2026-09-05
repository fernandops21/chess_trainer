from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import AttemptIn, AttemptOut, TacticOut, TacticsStatusOut, ThemeCountOut, ThemeStatOut
from chess_trainer.config import load_settings, set_setting
from chess_trainer.core.models import LichessPuzzle, TrainingSession, utcnow
from chess_trainer.core.stats import theme_stats
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.importer import DownloadCancelled, ImportFilter, download_file, import_csv_zst
from chess_trainer.core.tactics.service import (
    pick_next,
    record_attempt,
    refresh_counts_cache,
    tactics_status,
    theme_counts,
)
from chess_trainer.core.tactics.themes import THEME_LABELS

router = APIRouter(prefix="/api")


def _csv(value: str | None) -> list[str]:
    return [item for item in (v.strip() for v in (value or "").split(",")) if item]


@router.get("/tactics/status", response_model=TacticsStatusOut)
def get_status(db: Session = Depends(get_db)):
    return tactics_status(db, utcnow())


@router.post("/tactics/import", status_code=202)
def post_import(request: Request):
    app = request.app
    source = app.state.tactics_source
    dest = app.state.tactics_dest

    def job(progress):
        session = app.state.session_factory()
        try:
            s = load_settings(session)
            path = Path(source)
            if not path.is_file():
                path = download_file(str(source), Path(dest), progress, should_stop=app.state.jobs.should_stop)
            flt = ImportFilter(min_plays=s.lichess_min_plays, min_popularity=s.lichess_min_popularity)
            stats = import_csv_zst(session, path, flt, progress, should_stop=app.state.jobs.should_stop)
            if not stats.cancelled:
                set_setting(session, "lichess_imported_at", utcnow().isoformat())
                set_setting(session, "lichess_source_rows", stats.rows_read)
                # total e temas ficam em cache: contar 3,9 M linhas a cada tela de status é caro
                refresh_counts_cache(session)
            progress("import", stats.rows_read, stats.rows_read,
                     f"{stats.imported} táticas novas de {stats.rows_read} linhas" + (" (cancelado)" if stats.cancelled else ""))
        except DownloadCancelled:
            # cancelar não é erro: o JobRunner encerra em "idle" com a mensagem "cancelado"
            progress("download", 0, 0, "download cancelado")
            return
        finally:
            session.close()

    if not app.state.jobs.submit("import_lichess", job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": "import_lichess"}


@router.get("/tactics/next", response_model=TacticOut)
def get_next(themes: str | None = None, exclude: str | None = None, db: Session = Depends(get_db)):
    # checagem barata: um COUNT(*) na tabela de milhões de táticas custaria caro por requisição
    if db.scalar(select(LichessPuzzle.id).limit(1)) is None:
        raise HTTPException(404, "banco de táticas não importado; baixe em Configurações")
    settings = load_settings(db)
    row = pick_next(db, settings, utcnow(), themes=_csv(themes), exclude=_csv(exclude))
    if row is None:
        raise HTTPException(404, "nenhuma tática disponível com esses filtros")
    try:
        return asdict(to_tactic(row))
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/tactics/attempts", response_model=AttemptOut, status_code=201)
def post_attempt(body: AttemptIn, db: Session = Depends(get_db)):
    if body.session_id is not None and db.get(TrainingSession, body.session_id) is None:
        raise HTTPException(404, "sessão não encontrada")
    try:
        a = record_attempt(db, body.puzzle_id, correct=body.correct, used_hint=body.used_hint,
                           duration_ms=body.duration_ms, session_id=body.session_id, now=utcnow(), settings=load_settings(db))
    except KeyError as exc:
        raise HTTPException(404, "tática não encontrada") from exc
    return AttemptOut(id=a.id, puzzle_id=a.puzzle_id, correct=a.correct, used_hint=a.used_hint,
                      rating_before=a.rating_before, rating_after=a.rating_after,
                      delta=a.rating_after - a.rating_before, puzzle_rating=a.puzzle_rating)


@router.get("/tactics/themes", response_model=list[ThemeCountOut])
def get_themes(db: Session = Depends(get_db)):
    return [ThemeCountOut(theme=t, label=THEME_LABELS.get(t, t), count=n) for t, n in theme_counts(db)]


@router.get("/stats/themes", response_model=list[ThemeStatOut])
def get_theme_stats(days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)):
    return theme_stats(db, since=utcnow() - timedelta(days=days))
