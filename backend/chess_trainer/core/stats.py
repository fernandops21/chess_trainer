from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.core.models import LichessPuzzle, Puzzle, Review, TacticsAttempt
from chess_trainer.core.tactics.themes import THEME_LABELS, normalize_own_theme, primary_theme


def theme_stats(db: Session, since: datetime) -> list[dict]:
    """Acerto por tema desde `since`, juntando revisões dos puzzles próprios e tentativas do Lichess."""
    acc: dict[str, dict] = defaultdict(lambda: {"attempts": 0, "correct": 0, "own": 0, "lichess": 0})
    own = db.execute(select(Puzzle.theme, Review.result, Review.used_hint).join(Review, Review.puzzle_id == Puzzle.id)
                     .where(Review.reviewed_at >= since)).all()
    for theme, result, used_hint in own:
        t = normalize_own_theme(theme)
        acc[t]["attempts"] += 1
        acc[t]["own"] += 1
        acc[t]["correct"] += int(result == "correct" and not used_hint)
    lichess = db.execute(select(LichessPuzzle.themes, TacticsAttempt.correct, TacticsAttempt.used_hint)
                         .join(TacticsAttempt, TacticsAttempt.puzzle_id == LichessPuzzle.id)
                         .where(TacticsAttempt.attempted_at >= since)).all()
    for themes, correct, used_hint in lichess:
        t = primary_theme(themes.split())
        acc[t]["attempts"] += 1
        acc[t]["lichess"] += 1
        acc[t]["correct"] += int(correct and not used_hint)
    rows = [{"theme": t, "label": THEME_LABELS.get(t, t), "accuracy": v["correct"] / v["attempts"], **v} for t, v in acc.items()]
    rows.sort(key=lambda r: (-r["attempts"], r["theme"]))
    return rows
