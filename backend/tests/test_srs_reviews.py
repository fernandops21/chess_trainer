from datetime import datetime, timedelta

from sqlalchemy import func, select

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Review
from chess_trainer.core.srs.reviews import record_review, unleech
from tests.factories import make_puzzle

NOW = datetime(2026, 9, 4, 15, 0)
S = AppSettings(leech_lapses=3)


def test_record_review_updates_cache_and_logs(db_session):
    p = make_puzzle(db_session, fen="f1")
    r = record_review(db_session, p, session_id=None, correct=True, used_hint=False,
                      duration_ms=5000, now=NOW, settings=S)
    assert (p.srs_interval_days, p.srs_lapses, p.srs_ease) == (1, 0, 2.6)
    assert p.srs_due_at == NOW + timedelta(days=1) and p.srs_last_reviewed_at == NOW
    assert r.result == "correct" and r.interval_days == 1 and r.ease == 2.6 and r.puzzle_id == p.id


def test_hint_is_logged_as_correct_but_scheduled_as_fail(db_session):
    p = make_puzzle(db_session, fen="f1")
    r = record_review(db_session, p, session_id=None, correct=True, used_hint=True,
                      duration_ms=5000, now=NOW, settings=S)
    assert r.result == "correct" and r.used_hint is True
    assert p.srs_lapses == 1 and p.srs_ease == 2.3


def test_leech_after_configured_lapses(db_session):
    p = make_puzzle(db_session, fen="f1")
    for i in range(3):
        record_review(db_session, p, session_id=None, correct=False, used_hint=False,
                      duration_ms=1000, now=NOW + timedelta(days=i), settings=S)
    assert p.is_leech is True and p.leech_since == NOW + timedelta(days=2)
    assert db_session.scalar(select(func.count(Review.id))) == 3

    unleech(db_session, p, NOW + timedelta(days=5))
    assert p.is_leech is False and p.leech_since is None
    assert p.srs_lapses == 0 and p.srs_due_at == NOW + timedelta(days=5)
    assert p.srs_ease == 1.9  # mantida
