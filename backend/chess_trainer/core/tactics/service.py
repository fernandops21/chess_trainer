from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, get_setting, set_setting
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, TacticsAttempt
from chess_trainer.core.srs.queue import local_day_start
from chess_trainer.core.tactics.rating import elo_update

WIDEN_STEP = 100
MAX_WINDOW = 1200
FAILED_COOLDOWN = timedelta(days=1)
SAMPLE = 50


def _candidates(db: Session, lo: int, hi: int, themes: Sequence[str], exclude: Sequence[str], now: datetime):
    q = select(LichessPuzzle.id).where(LichessPuzzle.rating.between(lo, hi))
    if themes:
        q = q.where(LichessPuzzle.id.in_(select(LichessPuzzleTheme.puzzle_id).where(LichessPuzzleTheme.theme.in_(list(themes)))))
    if exclude:
        q = q.where(LichessPuzzle.id.not_in(list(exclude)))
    solved = select(TacticsAttempt.puzzle_id).where(TacticsAttempt.correct.is_(True))
    recent_fail = select(TacticsAttempt.puzzle_id).where(TacticsAttempt.attempted_at > now - FAILED_COOLDOWN)
    q = q.where(LichessPuzzle.id.not_in(solved)).where(LichessPuzzle.id.not_in(recent_fail))
    return q


def pick_next(db: Session, settings: AppSettings, now: datetime, themes: Sequence[str] = (),
              exclude: Sequence[str] = ()) -> LichessPuzzle | None:
    """Sorteia uma tática na janela de rating; errados antigos têm prioridade; alarga a janela se vazio."""
    window = settings.tactics_window
    while window <= MAX_WINDOW:
        lo, hi = settings.tactics_rating - window, settings.tactics_rating + window
        base = _candidates(db, lo, hi, themes, exclude, now)
        failed = base.where(exists().where(TacticsAttempt.puzzle_id == LichessPuzzle.id))
        ids = db.scalars(failed.order_by(func.random()).limit(SAMPLE)).all()
        if not ids:
            ids = db.scalars(base.order_by(func.random()).limit(SAMPLE)).all()
        if ids:
            return db.get(LichessPuzzle, ids[0])
        if db.scalar(select(func.count(LichessPuzzle.id))) == 0:
            return None
        window += WIDEN_STEP
    return None


def record_attempt(db: Session, puzzle_id: str, *, correct: bool, used_hint: bool, duration_ms: int,
                   session_id: str | None, now: datetime, settings: AppSettings) -> TacticsAttempt:
    puzzle = db.get(LichessPuzzle, puzzle_id)
    if puzzle is None:
        raise KeyError(puzzle_id)
    before = int(get_setting(db, "tactics_rating", settings.tactics_rating))
    after = elo_update(before, puzzle.rating, correct and not used_hint)
    attempt = TacticsAttempt(puzzle_id=puzzle_id, session_id=session_id, attempted_at=now, correct=correct,
                             used_hint=used_hint, duration_ms=duration_ms, rating_before=before, rating_after=after,
                             puzzle_rating=puzzle.rating)
    db.add(attempt)
    db.commit()
    set_setting(db, "tactics_rating", after)
    return attempt


def theme_counts(db: Session) -> list[tuple[str, int]]:
    rows = db.execute(select(LichessPuzzleTheme.theme, func.count()).group_by(LichessPuzzleTheme.theme)
                      .order_by(func.count().desc())).all()
    return [(t, int(n)) for t, n in rows]


def tactics_status(db: Session, now: datetime) -> dict:
    count = int(db.scalar(select(func.count(LichessPuzzle.id))) or 0)
    settings_rating = get_setting(db, "tactics_rating", AppSettings().tactics_rating)
    day = local_day_start(now)
    return {
        "imported": count > 0,
        "count": count,
        "imported_at": get_setting(db, "lichess_imported_at"),
        "source_rows": get_setting(db, "lichess_source_rows"),
        "rating": int(settings_rating),
        "window": int(get_setting(db, "tactics_window", AppSettings().tactics_window)),
        "attempts_total": int(db.scalar(select(func.count(TacticsAttempt.id))) or 0),
        "attempts_today": int(db.scalar(select(func.count(TacticsAttempt.id)).where(TacticsAttempt.attempted_at >= day)) or 0),
        "correct_30d": int(db.scalar(select(func.count(TacticsAttempt.id)).where(
            TacticsAttempt.attempted_at >= now - timedelta(days=30), TacticsAttempt.correct.is_(True),
            TacticsAttempt.used_hint.is_(False))) or 0),
        "attempts_30d": int(db.scalar(select(func.count(TacticsAttempt.id)).where(
            TacticsAttempt.attempted_at >= now - timedelta(days=30))) or 0),
    }
