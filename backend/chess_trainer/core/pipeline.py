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
from chess_trainer.core.puzzles.service import generate_puzzles_for_game

ProgressFn = Callable[[str, int, int, str], None]


def analyze_pending(
    db: Session,
    engine: EngineLike,
    settings: AppSettings,
    progress: ProgressFn | None = None,
    limit: int | None = None,
) -> int:
    thresholds = thresholds_from(settings)
    cfg = puzzle_config_from(settings)
    games = db.scalars(
        select(Game).where(Game.analyzed_at.is_(None)).order_by(Game.played_at.desc())
    ).all()
    if limit is not None:
        games = games[:limit]

    analyzed = 0
    for i, game in enumerate(games):
        if progress:
            progress("analyze", i, len(games), f"{game.white} x {game.black}")
        try:
            data = analyze_game(game.pgn, engine, settings.analysis_depth)
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

        rows = [Position(game_id=game.id, **asdict(d)) for d in data]
        classify_positions(rows, game.my_color, thresholds)
        db.add_all(rows)
        game.analyzed_at = utcnow()
        game.analysis_depth = settings.analysis_depth
        db.flush()
        try:
            generate_puzzles_for_game(db, game, engine, cfg)
        except chess.engine.EngineError:
            db.rollback()
            engine.restart()
            continue
        db.commit()
        analyzed += 1

    if progress:
        progress("analyze", len(games), len(games), "concluído")
    return analyzed
