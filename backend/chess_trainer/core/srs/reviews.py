from datetime import datetime

from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Puzzle, Review
from chess_trainer.core.srs.scheduler import SrsState, next_state


def record_review(
    db: Session,
    puzzle: Puzzle,
    *,
    session_id: str | None,
    correct: bool,
    used_hint: bool,
    duration_ms: int,
    now: datetime,
    settings: AppSettings,
) -> Review:
    prev = SrsState(
        ease=puzzle.srs_ease,
        interval_days=puzzle.srs_interval_days,
        lapses=puzzle.srs_lapses,
        due_at=puzzle.srs_due_at,
        last_reviewed_at=puzzle.srs_last_reviewed_at,
    )
    nxt = next_state(prev, correct=correct, used_hint=used_hint, duration_ms=duration_ms,
                     solver_moves=puzzle.solver_moves, reviewed_at=now)
    puzzle.srs_ease = nxt.ease
    puzzle.srs_interval_days = nxt.interval_days
    puzzle.srs_lapses = nxt.lapses
    puzzle.srs_due_at = nxt.due_at
    puzzle.srs_last_reviewed_at = nxt.last_reviewed_at
    if nxt.lapses >= settings.leech_lapses and not puzzle.is_leech:
        puzzle.is_leech = True
        puzzle.leech_since = now

    review = Review(
        puzzle_id=puzzle.id,
        session_id=session_id,
        reviewed_at=now,
        result="correct" if correct else "wrong",
        used_hint=used_hint,
        duration_ms=duration_ms,
        ease=nxt.ease,
        interval_days=nxt.interval_days,
        due_at=nxt.due_at,
        lapses=nxt.lapses,
    )
    db.add(review)
    db.commit()
    return review


def unleech(db: Session, puzzle: Puzzle, now: datetime) -> None:
    puzzle.is_leech = False
    puzzle.leech_since = None
    puzzle.srs_lapses = 0
    puzzle.srs_due_at = now
    db.commit()
