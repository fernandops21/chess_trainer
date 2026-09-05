from dataclasses import asdict
from typing import Callable

import chess.engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, puzzle_config_from, thresholds_from
from chess_trainer.core.analysis.engine import EngineLike
from chess_trainer.core.analysis.game_analyzer import analyze_game
from chess_trainer.core.analysis.mistakes import classify_positions
from chess_trainer.core.models import Game, Position, utcnow
from chess_trainer.core.puzzles.service import draft_puzzles, persist_drafts

ProgressFn = Callable[[str, int, int, str], None]
StopFn = Callable[[], bool]


def analyze_pending(
    db: Session,
    engine: EngineLike,
    settings: AppSettings,
    progress: ProgressFn | None = None,
    limit: int | None = None,
    should_stop: StopFn | None = None,
    game_id: str | None = None,
) -> int:
    thresholds = thresholds_from(settings)
    cfg = puzzle_config_from(settings)
    stmt = select(Game).where(Game.analyzed_at.is_(None)).order_by(Game.played_at.desc())
    if game_id is not None:
        stmt = stmt.where(Game.id == game_id)
    games = db.scalars(stmt).all()
    if limit is not None:
        games = games[:limit]

    analyzed = 0
    for i, game in enumerate(games):
        if should_stop is not None and should_stop():
            if progress:
                progress("analyze", i, len(games), "cancelado")
            return analyzed
        if progress:
            progress("analyze", i, len(games), f"{game.white} x {game.black}")

        # Fase de engine: nada é escrito no banco enquanto o Stockfish pensa, para que
        # o SQLite não fique travado por minutos e outras requisições possam gravar.
        try:
            data = analyze_game(
                game.pgn, engine, settings.analysis_depth, max_seconds=settings.analysis_seconds,
            )
        except ValueError:
            game.analyzed_at = utcnow()
            game.analysis_depth = 0
            db.commit()
            analyzed += 1
            continue
        except chess.engine.EngineError:
            db.rollback()
            engine.restart()
            continue

        rows = [Position(game_id=game.id, **asdict(d)) for d in data]  # transientes: fora da sessão
        classify_positions(rows, game.my_color, thresholds)
        try:
            drafts = draft_puzzles(rows, engine, cfg, should_stop=should_stop)
        except chess.engine.EngineError:
            db.rollback()
            engine.restart()
            continue

        if drafts is None:
            db.rollback()
            if progress:
                progress("analyze", i, len(games), "cancelado")
            return analyzed

        # Fase de escrita: curta, sem nenhuma chamada à engine no meio.
        db.add_all(rows)
        db.flush()  # atribui os ids das posições usados pelos puzzles
        persist_drafts(db, game, drafts)
        game.analyzed_at = utcnow()
        game.analysis_depth = settings.analysis_depth
        db.commit()
        analyzed += 1

    if progress:
        progress("analyze", len(games), len(games), "concluído")
    return analyzed
