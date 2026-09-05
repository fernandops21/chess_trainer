from datetime import timedelta

from chess_trainer.config import AppSettings, get_setting
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, TacticsAttempt, utcnow
from chess_trainer.core.tactics.service import pick_next, record_attempt, tactics_status, theme_counts

FEN = "8/8/8/8/8/8/8/K6k w - - 0 1"


def add(db, pid: str, rating: int, themes: str = "endgame"):
    db.add(LichessPuzzle(id=pid, fen=FEN, moves="a1a2 h1h2", rating=rating, rating_deviation=50, popularity=90,
                         nb_plays=500, themes=themes, opening_tags=""))
    for t in themes.split():
        db.add(LichessPuzzleTheme(theme=t, puzzle_id=pid))
    db.commit()


def test_pick_within_window(db_session):
    add(db_session, "low", 800); add(db_session, "mid", 1250); add(db_session, "high", 1900)
    s = AppSettings(tactics_rating=1200, tactics_window=150)
    picks = {pick_next(db_session, s, utcnow()).id for _ in range(10)}
    assert picks == {"mid"}


def test_pick_widens_window_when_empty(db_session):
    add(db_session, "far", 2000)
    s = AppSettings(tactics_rating=1200, tactics_window=100)
    assert pick_next(db_session, s, utcnow()).id == "far"


def test_pick_filters_by_theme_and_exclude(db_session):
    add(db_session, "a", 1200, "fork middlegame"); add(db_session, "b", 1200, "pin middlegame"); add(db_session, "c", 1200, "fork endgame")
    s = AppSettings()
    assert {pick_next(db_session, s, utcnow(), themes=["fork"]).id for _ in range(10)} <= {"a", "c"}
    assert pick_next(db_session, s, utcnow(), themes=["fork"], exclude=["a"]).id == "c"
    assert pick_next(db_session, s, utcnow(), themes=["skewer"]) is None


def test_pick_skips_solved_and_prefers_old_failures(db_session):
    add(db_session, "solved", 1200); add(db_session, "failed", 1200); add(db_session, "fresh", 1200)
    now = utcnow()
    db_session.add(TacticsAttempt(puzzle_id="solved", correct=True, rating_before=1200, rating_after=1216, puzzle_rating=1200,
                                  attempted_at=now - timedelta(days=3)))
    db_session.add(TacticsAttempt(puzzle_id="failed", correct=False, rating_before=1200, rating_after=1184, puzzle_rating=1200,
                                  attempted_at=now - timedelta(days=2)))
    db_session.commit()
    s = AppSettings()
    assert {pick_next(db_session, s, now).id for _ in range(10)} == {"failed"}
    # errado há menos de um dia ainda não volta
    db_session.query(TacticsAttempt).filter_by(puzzle_id="failed").update({"attempted_at": now - timedelta(hours=2)})
    db_session.commit()
    assert {pick_next(db_session, s, now).id for _ in range(10)} == {"fresh"}


def test_record_attempt_updates_rating(db_session):
    add(db_session, "p", 1200)
    s = AppSettings(tactics_rating=1200)
    a = record_attempt(db_session, "p", correct=True, used_hint=False, duration_ms=900, session_id=None, now=utcnow(), settings=s)
    assert (a.rating_before, a.rating_after, a.puzzle_rating) == (1200, 1216, 1200)
    assert get_setting(db_session, "tactics_rating") == 1216
    b = record_attempt(db_session, "p", correct=True, used_hint=True, duration_ms=900, session_id=None, now=utcnow(), settings=AppSettings(tactics_rating=1216))
    assert b.rating_after < 1216  # dica conta como erro


def test_theme_counts_and_status(db_session):
    add(db_session, "a", 1200, "fork middlegame"); add(db_session, "b", 1300, "fork endgame")
    assert theme_counts(db_session)[0] == ("fork", 2)
    st = tactics_status(db_session, utcnow())
    assert st["imported"] is True and st["count"] == 2 and st["attempts_today"] == 0 and st["rating"] == 1200
