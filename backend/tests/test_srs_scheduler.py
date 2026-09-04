from datetime import datetime, timedelta

from chess_trainer.core.srs.scheduler import SrsState, next_state

T0 = datetime(2026, 9, 4, 12, 0)
SLOW = 60_000


def _pass(prev, at, duration_ms=SLOW, moves=1):
    return next_state(prev, correct=True, used_hint=False, duration_ms=duration_ms, solver_moves=moves, reviewed_at=at)


def _fail(prev, at):
    return next_state(prev, correct=False, used_hint=False, duration_ms=SLOW, solver_moves=1, reviewed_at=at)


def test_progression_on_time():
    s = _pass(SrsState(), T0)
    assert (s.interval_days, s.ease, s.lapses) == (1, 2.5, 0)
    assert s.due_at == T0 + timedelta(days=1) and s.last_reviewed_at == T0
    s = _pass(s, T0 + timedelta(days=1))
    assert s.interval_days == 3
    s = _pass(s, T0 + timedelta(days=4))
    assert s.interval_days == 8            # round(3 × 2.5)
    s = _pass(s, T0 + timedelta(days=12))
    assert s.interval_days == 20           # round(8 × 2.5)


def test_late_review_uses_real_elapsed_interval():
    s = SrsState(ease=2.5, interval_days=3, lapses=0, due_at=T0 + timedelta(days=3), last_reviewed_at=T0)
    late = _pass(s, T0 + timedelta(days=13))
    assert late.interval_days == 33        # round(13 × 2.5), não 8


def test_fail_resets_interval_and_lowers_ease():
    s = SrsState(ease=2.5, interval_days=20, lapses=1, due_at=T0, last_reviewed_at=T0 - timedelta(days=20))
    f = _fail(s, T0)
    assert (f.interval_days, f.ease, f.lapses) == (1, 2.3, 2)
    assert f.due_at == T0 + timedelta(days=1)


def test_hint_counts_as_fail():
    s = next_state(SrsState(ease=2.5, interval_days=8), correct=True, used_hint=True,
                   duration_ms=1000, solver_moves=1, reviewed_at=T0)
    assert (s.interval_days, s.ease, s.lapses) == (1, 2.3, 1)


def test_ease_floor():
    assert _fail(SrsState(ease=1.4), T0).ease == 1.3
    assert _fail(SrsState(ease=1.3), T0).ease == 1.3


def test_fast_answer_bonus():
    fast = _pass(SrsState(), T0, duration_ms=9_000, moves=1)
    assert fast.ease == 2.6
    fast3 = _pass(SrsState(), T0, duration_ms=29_000, moves=3)
    assert fast3.ease == 2.6
    slow3 = _pass(SrsState(), T0, duration_ms=31_000, moves=3)
    assert slow3.ease == 2.5


def test_bonus_applies_after_interval_computation():
    s = SrsState(ease=2.5, interval_days=3, last_reviewed_at=T0 - timedelta(days=3))
    r = _pass(s, T0, duration_ms=1_000)
    assert r.interval_days == 8 and r.ease == 2.6


def test_interval_always_grows_on_pass():
    s = SrsState(ease=1.3, interval_days=3, last_reviewed_at=T0 - timedelta(days=3))
    assert _pass(s, T0).interval_days == 4   # round(3 × 1.3) = 4 ≥ 3 + 1
