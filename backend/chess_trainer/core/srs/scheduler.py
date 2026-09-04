from dataclasses import dataclass
from datetime import datetime, timedelta

MIN_EASE = 1.3
FAST_MS_PER_MOVE = 10_000


@dataclass(frozen=True)
class SrsState:
    ease: float = 2.5
    interval_days: int = 0
    lapses: int = 0
    due_at: datetime | None = None
    last_reviewed_at: datetime | None = None


def next_state(
    prev: SrsState,
    *,
    correct: bool,
    used_hint: bool,
    duration_ms: int,
    solver_moves: int,
    reviewed_at: datetime,
) -> SrsState:
    passed = correct and not used_hint
    if not passed:
        ease = max(MIN_EASE, round(prev.ease - 0.2, 2))
        interval = 1
        lapses = prev.lapses + 1
    else:
        if prev.interval_days == 0:
            interval = 1
        elif prev.interval_days == 1:
            interval = 3
        else:
            actual = prev.interval_days
            if prev.last_reviewed_at is not None:
                actual = max(actual, (reviewed_at - prev.last_reviewed_at).days)
            interval = max(prev.interval_days + 1, int(actual * prev.ease + 0.5))
        fast = duration_ms <= FAST_MS_PER_MOVE * max(1, solver_moves)
        ease = round(prev.ease + 0.1, 2) if fast else prev.ease
        lapses = prev.lapses
    return SrsState(
        ease=ease,
        interval_days=interval,
        lapses=lapses,
        due_at=reviewed_at + timedelta(days=interval),
        last_reviewed_at=reviewed_at,
    )
