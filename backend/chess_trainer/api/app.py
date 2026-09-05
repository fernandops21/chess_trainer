import os
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from chess_trainer.api.jobs import JobRunner
from chess_trainer.api.routes import games, system, training
from chess_trainer.config import AppSettings
from chess_trainer.core.analysis.engine import EngineLike, StockfishEngine, find_stockfish
from chess_trainer.core.db import init_db, make_engine, make_session_factory
from chess_trainer.core.importers.chesscom import ChessComClient

USER_AGENT = "chess-trainer/0.1 (local)"
BACKEND_DIR = Path(__file__).resolve().parents[2]


class SpaStaticFiles(StaticFiles):
    """Serve os estáticos e devolve index.html para rotas do SPA."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # `path` já vem normalizado pelo StaticFiles com o separador do SO
            # (no Windows, "assets\app.js"), então comparamos com "/".
            url_path = path.replace(os.sep, "/")
            # `assets/` fica de fora: um index.html em cache pode pedir um bundle
            # antigo e receber HTML no lugar do módulo JS.
            if exc.status_code == 404 and not url_path.startswith(("api", "assets/")):
                return await super().get_response("index.html", scope)
            raise


def default_engine_factory(settings: AppSettings) -> EngineLike | None:
    path = find_stockfish(settings.stockfish_path)
    return StockfishEngine(path) if path else None


def default_chesscom_factory(settings: AppSettings) -> ChessComClient:
    return ChessComClient(USER_AGENT)


def _probe_engine_factory(engine_factory):
    def probe(settings: AppSettings) -> tuple[bool, str | None]:
        engine = engine_factory(settings)
        available = engine is not None
        if engine is not None:
            engine.close()
        return available, "fake"

    return probe


def create_app(
    db_path: str | None = None,
    engine_factory=None,
    chesscom_factory=None,
    dist_dir: str | Path | None = None,
) -> FastAPI:
    if db_path is None:
        db_path = os.environ.get("CHESS_TRAINER_DB", str(BACKEND_DIR / "data" / "chess_trainer.db"))
    db_engine = make_engine(db_path)
    init_db(db_engine)

    app = FastAPI(title="Chess Trainer", version="0.1.0")
    app.state.session_factory = make_session_factory(db_engine)
    app.state.jobs = JobRunner()
    app.state.engine_factory = engine_factory or default_engine_factory
    app.state.chesscom_factory = chesscom_factory or default_chesscom_factory
    if engine_factory is not None:
        # em testes a disponibilidade da engine é decidida pela factory, não pelo disco
        app.state.engine_probe = _probe_engine_factory(engine_factory)

    app.include_router(system.router)
    app.include_router(games.router)
    app.include_router(training.router)

    dist = Path(dist_dir) if dist_dir is not None else BACKEND_DIR.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", SpaStaticFiles(directory=str(dist), html=True), name="frontend")
    return app
