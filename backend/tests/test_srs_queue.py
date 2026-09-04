from datetime import datetime, timedelta

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Review
from chess_trainer.core.srs.queue import QueueFilters, build_queue, count_new_reviewed_today, local_day_start
from tests.factories import make_puzzle

NOW = datetime(2026, 9, 4, 15, 0)
S = AppSettings(new_per_day=2)


def test_local_day_start_is_within_last_24h():
    start = local_day_start(NOW)
    assert start <= NOW and NOW - start < timedelta(hours=24)
    assert start.tzinfo is None
    from datetime import timezone
    start_local = start.replace(tzinfo=timezone.utc).astimezone()
    now_local = NOW.replace(tzinfo=timezone.utc).astimezone()
    assert (start_local.hour, start_local.minute, start_local.second) == (0, 0, 0)
    assert start_local.date() == now_local.date()


def test_due_puzzles_first_most_overdue_first(db_session):
    p_late = make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=3))
    p_soon = make_puzzle(db_session, fen="f2", due_at=NOW - timedelta(hours=1))
    make_puzzle(db_session, fen="f3", due_at=NOW + timedelta(days=1))  # ainda não venceu
    make_puzzle(db_session, fen="f4")                                   # novo
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert [p.id for p in q.due] == [p_late.id, p_soon.id]
    assert q.due_count == 2 and q.new == [] and q.new_available == 1


def test_new_only_when_nothing_due_recent_games_first_limited(db_session):
    old = make_puzzle(db_session, fen="f1", played_at=datetime(2026, 1, 1))
    mid = make_puzzle(db_session, fen="f2", played_at=datetime(2026, 5, 1))
    new = make_puzzle(db_session, fen="f3", played_at=datetime(2026, 8, 1))
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert q.due == [] and [p.id for p in q.new] == [new.id, mid.id]
    assert q.new_available == 3 and q.new_remaining_today == 2


def test_new_limit_discounts_new_reviewed_today(db_session):
    reviewed = make_puzzle(db_session, fen="f0", due_at=NOW + timedelta(days=1))
    db_session.add(Review(puzzle_id=reviewed.id, reviewed_at=NOW - timedelta(hours=2), result="correct",
                          ease=2.5, interval_days=1, due_at=NOW + timedelta(days=1), lapses=0))
    db_session.commit()
    make_puzzle(db_session, fen="f1"); make_puzzle(db_session, fen="f2")
    assert count_new_reviewed_today(db_session, NOW) == 1
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert len(q.new) == 1 and q.new_remaining_today == 1


def test_filters_and_leeches(db_session):
    make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=1), category="rapid", theme="fork", kind="punish", side="white")
    make_puzzle(db_session, fen="f2", due_at=NOW - timedelta(days=1), category="blitz", theme="fork", kind="avoid", side="black")
    make_puzzle(db_session, fen="f3", due_at=NOW - timedelta(days=1), is_leech=True)
    assert build_queue(db_session, QueueFilters(), S, NOW).due_count == 2
    assert build_queue(db_session, QueueFilters(category="blitz"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(theme="fork", kind="avoid"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(color="white"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(theme="pin"), S, NOW).due_count == 0
