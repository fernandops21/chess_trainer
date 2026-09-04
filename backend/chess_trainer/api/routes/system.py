from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import SettingsIn, SettingsOut
from chess_trainer.config import AppSettings, get_setting, load_settings, save_settings, set_setting
from chess_trainer.core.analysis.engine import find_stockfish
from chess_trainer.core.importers.service import import_games
from chess_trainer.core.models import Game, utcnow
from chess_trainer.core.pipeline import analyze_pending
from chess_trainer.core.puzzles.service import regenerate_all

router = APIRouter(prefix="/api")


def _engine_available(request: Request, settings: AppSettings) -> tuple[bool, str | None]:
    probe = getattr(request.app.state, "engine_probe", None)
    if probe is not None:
        return probe(settings)
    path = find_stockfish(settings.stockfish_path)
    return path is not None, path


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)):
    settings = load_settings(db)
    available, path = _engine_available(request, settings)
    total = db.scalar(select(func.count(Game.id))) or 0
    pending = db.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_(None))) or 0
    last_import = get_setting(db, "last_import_at")
    return {
        "engine": {"available": available, "path": path},
        "job": request.app.state.jobs.snapshot(),
        "games_total": total,
        "games_pending": pending,
        "last_import_at": last_import,
    }


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return asdict(load_settings(db))


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    current = load_settings(db)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(current, key, value)
    return asdict(save_settings(db, current))


def _submit(request: Request, name: str, fn) -> dict:
    if not request.app.state.jobs.submit(name, fn):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": name}


@router.post("/import", status_code=202)
def post_import(request: Request, db: Session = Depends(get_db)):
    settings = load_settings(db)
    if not settings.chesscom_username:
        raise HTTPException(400, "configure o usuário do chess.com primeiro")
    app = request.app

    def job(progress):
        session = app.state.session_factory()
        try:
            s = load_settings(session)
            client = app.state.chesscom_factory(s)
            import_games(session, client, s, progress)
            set_setting(session, "last_import_at", utcnow().isoformat())
        finally:
            session.close()

    return _submit(request, "import", job)


def _engine_job(request: Request, name: str, work):
    db = request.app.state.session_factory()
    try:
        settings = load_settings(db)
    finally:
        db.close()
    available, _ = _engine_available(request, settings)
    if not available:
        raise HTTPException(503, "Stockfish não encontrado; configure o caminho em /api/settings")
    app = request.app

    def job(progress):
        session = app.state.session_factory()
        engine = None
        try:
            s = load_settings(session)
            engine = app.state.engine_factory(s)
            if engine is None:
                raise RuntimeError("Stockfish não encontrado")
            work(session, engine, s, progress)
        finally:
            if engine is not None:
                engine.close()
            session.close()

    return _submit(request, name, job)


@router.post("/analyze", status_code=202)
def post_analyze(request: Request, limit: int | None = None):
    return _engine_job(request, "analyze",
                       lambda db, engine, s, progress: analyze_pending(db, engine, s, progress, limit))


@router.post("/puzzles/regenerate", status_code=202)
def post_regenerate(request: Request):
    return _engine_job(request, "regenerate",
                       lambda db, engine, s, progress: regenerate_all(db, engine, s, progress))
