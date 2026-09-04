from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Game, Puzzle, Review


def local_day_start(now_utc: datetime) -> datetime:
    local = now_utc.replace(tzinfo=timezone.utc).astimezone()
    midnight_naive_local = local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    # naive datetime .astimezone() é interpretado como hora local do sistema,
    # com o offset correto para aquele instante (resolve DST na meia-noite)
    return midnight_naive_local.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class QueueFilters:
    category: str | None = None
    theme: str | None = None
    kind: str | None = None
    color: str | None = None


@dataclass
class QueueResult:
    due: list[Puzzle]
    new: list[Puzzle]
    due_count: int
    new_available: int
    new_remaining_today: int


def _apply_filters(stmt: Select, f: QueueFilters) -> Select:
    if f.category:
        stmt = stmt.where(Puzzle.category == f.category)
    if f.theme:
        stmt = stmt.where(Puzzle.theme == f.theme)
    if f.kind:
        stmt = stmt.where(Puzzle.kind == f.kind)
    if f.color:
        stmt = stmt.where(Puzzle.side_to_move == f.color)
    return stmt


def count_new_reviewed_today(db: Session, now: datetime) -> int:
    day_start = local_day_start(now)
    first_reviews = (
        select(Review.puzzle_id, func.min(Review.reviewed_at).label("first_at"))
        .group_by(Review.puzzle_id)
        .subquery()
    )
    return int(db.scalar(select(func.count()).select_from(first_reviews).where(first_reviews.c.first_at >= day_start)) or 0)


def build_queue(db: Session, filters: QueueFilters, settings: AppSettings, now: datetime) -> QueueResult:
    base = _apply_filters(select(Puzzle).where(Puzzle.is_leech.is_(False)), filters)

    due = db.scalars(
        base.where(Puzzle.srs_due_at.is_not(None), Puzzle.srs_due_at <= now).order_by(Puzzle.srs_due_at)
    ).all()

    new_stmt = base.where(Puzzle.srs_due_at.is_(None)).join(Game, Game.id == Puzzle.game_id).order_by(Game.played_at.desc())
    new_available = int(db.scalar(select(func.count()).select_from(new_stmt.subquery())) or 0)
    remaining = max(0, settings.new_per_day - count_new_reviewed_today(db, now))

    new: list[Puzzle] = []
    if not due and remaining > 0:
        new = db.scalars(new_stmt.limit(remaining)).all()

    return QueueResult(due=list(due), new=list(new), due_count=len(due),
                       new_available=new_available, new_remaining_today=remaining)
