from datetime import timedelta

from chess_trainer.core.models import LichessPuzzle, Review, TacticsAttempt, utcnow
from chess_trainer.core.stats import theme_stats
from tests.factories import make_puzzle

FEN = "8/8/8/8/8/8/8/K6k w - - 0 1"


def test_theme_stats_merges_own_and_lichess(db_session):
    now = utcnow()
    own = make_puzzle(db_session, fen="r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", theme="fork")
    for ok in (True, False):
        db_session.add(Review(puzzle_id=own.id, result="correct" if ok else "wrong", ease=2.5, interval_days=1,
                              due_at=now, lapses=0, reviewed_at=now))
    db_session.add(LichessPuzzle(id="l1", fen=FEN, moves="a1a2 h1h2", rating=1200, rating_deviation=50, popularity=90,
                                 nb_plays=500, themes="fork middlegame", opening_tags=""))
    db_session.add(TacticsAttempt(puzzle_id="l1", correct=True, rating_before=1200, rating_after=1216, puzzle_rating=1200, attempted_at=now))
    db_session.add(TacticsAttempt(puzzle_id="l1", correct=True, rating_before=1200, rating_after=1216, puzzle_rating=1200,
                                  attempted_at=now - timedelta(days=40)))
    db_session.commit()
    rows = theme_stats(db_session, since=now - timedelta(days=30))
    fork = next(r for r in rows if r["theme"] == "fork")
    assert (fork["attempts"], fork["correct"], fork["own"], fork["lichess"]) == (3, 2, 2, 1)
    assert fork["label"] == "garfo" and abs(fork["accuracy"] - 2 / 3) < 1e-9
