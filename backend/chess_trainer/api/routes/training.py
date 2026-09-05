import json
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import (
    DashboardOut, GameRef, MistakeRef, PuzzleOut, PuzzleSibling, QueueOut, ReviewIn, ReviewOut, SessionIn, SessionOut, SrsOut,
)
from chess_trainer.config import get_setting, load_settings
from chess_trainer.core.models import Game, Puzzle, Review, TrainingSession, utcnow
from chess_trainer.core.srs.queue import QueueFilters, build_queue, local_day_start
from chess_trainer.core.srs.reviews import record_review, unleech

router = APIRouter(prefix="/api")


def _puzzle_out(p: Puzzle) -> PuzzleOut:
    return PuzzleOut(
        id=p.id, kind=p.kind, fen_start=p.fen_start, side_to_move=p.side_to_move,
        solution=p.solution_data, end_reason=p.end_reason, theme=p.theme, category=p.category,
        solver_moves=p.solver_moves, is_leech=p.is_leech,
        srs=SrsOut(ease=p.srs_ease, interval_days=p.srs_interval_days, lapses=p.srs_lapses,
                   due_at=p.srs_due_at, last_reviewed_at=p.srs_last_reviewed_at),
        game=GameRef(id=p.game.id, white=p.game.white, black=p.game.black, played_at=p.game.played_at,
                     source_id=p.game.source_id, my_color=p.game.my_color),
        ply=p.position.ply, move_played=p.position.move_played,
        mistake=MistakeRef(ply=p.position.ply, move_played=p.position.move_played, move_uci=p.position.move_uci,
                           eval_before=p.position.eval_before, eval_after=p.position.eval_after,
                           mistake_level=p.position.mistake_level, mistake_by=p.position.mistake_by),
        siblings=[PuzzleSibling(id=s.id, kind=s.kind) for s in p.position.puzzles if s.id != p.id],
    )


def _get_puzzle(db: Session, puzzle_id: str) -> Puzzle:
    puzzle = db.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise HTTPException(404, "puzzle não encontrado")
    return puzzle


@router.get("/puzzles/{puzzle_id}", response_model=PuzzleOut)
def get_puzzle(puzzle_id: str, db: Session = Depends(get_db)):
    return _puzzle_out(_get_puzzle(db, puzzle_id))


@router.get("/queue", response_model=QueueOut)
def get_queue(
    category: str | None = None, theme: str | None = None, kind: str | None = None, color: str | None = None,
    db: Session = Depends(get_db),
):
    result = build_queue(db, QueueFilters(category, theme, kind, color), load_settings(db), utcnow())
    items = result.due or result.new
    return QueueOut(due_count=result.due_count, new_available=result.new_available,
                    new_remaining_today=result.new_remaining_today, items=[_puzzle_out(p) for p in items])


@router.get("/leeches", response_model=list[PuzzleOut])
def get_leeches(db: Session = Depends(get_db)):
    puzzles = db.scalars(select(Puzzle).where(Puzzle.is_leech.is_(True)).order_by(Puzzle.leech_since.desc())).all()
    return [_puzzle_out(p) for p in puzzles]


@router.post("/puzzles/{puzzle_id}/unleech", response_model=PuzzleOut)
def post_unleech(puzzle_id: str, db: Session = Depends(get_db)):
    puzzle = _get_puzzle(db, puzzle_id)
    unleech(db, puzzle, utcnow())
    return _puzzle_out(puzzle)


def _session_out(db: Session, s: TrainingSession) -> SessionOut:
    rows = db.execute(
        select(func.count(Review.id), func.sum(Review.duration_ms),
               func.sum(case((Review.result == "correct", 1), else_=0)))
        .where(Review.session_id == s.id)
    ).one()
    return SessionOut(id=s.id, started_at=s.started_at, ended_at=s.ended_at, planned_minutes=s.planned_minutes,
                      filters=json.loads(s.filters or "{}"), reviews=int(rows[0] or 0),
                      correct=int(rows[2] or 0), total_duration_ms=int(rows[1] or 0))


@router.post("/sessions", response_model=SessionOut, status_code=201)
def post_session(body: SessionIn, db: Session = Depends(get_db)):
    s = TrainingSession(planned_minutes=body.planned_minutes, filters=json.dumps(body.filters))
    db.add(s)
    db.commit()
    return _session_out(db, s)


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
def end_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise HTTPException(404, "sessão não encontrada")
    if s.ended_at is None:
        s.ended_at = utcnow()
        db.commit()
    return _session_out(db, s)


@router.post("/reviews", response_model=ReviewOut, status_code=201)
def post_review(body: ReviewIn, db: Session = Depends(get_db)):
    puzzle = _get_puzzle(db, body.puzzle_id)
    if body.session_id is not None and db.get(TrainingSession, body.session_id) is None:
        raise HTTPException(404, "sessão não encontrada")
    review = record_review(db, puzzle, session_id=body.session_id, correct=body.correct,
                           used_hint=body.used_hint, duration_ms=body.duration_ms,
                           now=utcnow(), settings=load_settings(db))
    return ReviewOut(id=review.id, puzzle_id=puzzle.id, result=review.result, used_hint=review.used_hint,
                     ease=review.ease, interval_days=review.interval_days, due_at=review.due_at,
                     lapses=review.lapses, is_leech=puzzle.is_leech)


def _streak_days(db: Session, now) -> int:
    stamps = db.scalars(select(Review.reviewed_at)).all()
    days = {ts.replace(tzinfo=timezone.utc).astimezone().date() for ts in stamps}
    today = now.replace(tzinfo=timezone.utc).astimezone().date()
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    now = utcnow()
    settings = load_settings(db)
    queue = build_queue(db, QueueFilters(), settings, now)
    day_start = local_day_start(now)
    reviews_today = db.scalar(select(func.count(Review.id)).where(Review.reviewed_at >= day_start)) or 0
    last_import = get_setting(db, "last_import_at")
    return DashboardOut(
        due_today=queue.due_count,
        new_available=queue.new_available,
        new_remaining_today=queue.new_remaining_today,
        streak_days=_streak_days(db, now),
        reviews_today=int(reviews_today),
        last_import_at=last_import,
        games_total=int(db.scalar(select(func.count(Game.id))) or 0),
        games_analyzed=int(db.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_not(None))) or 0),
        puzzles_total=int(db.scalar(select(func.count(Puzzle.id))) or 0),
        leeches=int(db.scalar(select(func.count(Puzzle.id)).where(Puzzle.is_leech.is_(True))) or 0),
    )
