from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.core.models import LichessPuzzle, Puzzle, Review, TacticsAttempt
from chess_trainer.core.srs.queue import local_day
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


SOURCES = ("own", "lichess", "study")


def streak_days(db: Session, now: datetime) -> int:
    """Dias locais seguidos com pelo menos uma revisão, contando de hoje (ou de ontem) para trás."""
    stamps = db.scalars(select(Review.reviewed_at)).all()
    days = {local_day(ts) for ts in stamps}
    today = local_day(now)
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def progress(db: Session, since: datetime, now: datetime) -> dict:
    """Números da página de progresso no período: só leitura, nada é gravado.

    `reviews_per_day` agrupa pelo dia local (as datas do banco são naive/UTC) e
    omite os dias sem revisão — quem desenha o gráfico decide o que fazer com os
    buracos. `tactics_rating` traz um ponto por tentativa, em ordem cronológica.
    """
    rows = db.execute(
        select(Review.reviewed_at, Review.result, Review.used_hint, Puzzle.source)
        .join(Puzzle, Puzzle.id == Review.puzzle_id)
        .where(Review.reviewed_at >= since)
        .order_by(Review.reviewed_at)
    ).all()

    per_day: dict[str, dict] = {}
    by_source = {source: {"reviews": 0, "correct": 0} for source in SOURCES}
    reviews = correct = 0
    for reviewed_at, result, used_hint, source in rows:
        # "certa" aqui é a mesma de `theme_stats`: acertar com dica não conta como acerto
        ok = result == "correct" and not used_hint
        day = per_day.setdefault(local_day(reviewed_at).isoformat(), {"correct": 0, "wrong": 0})
        day["correct" if ok else "wrong"] += 1
        bucket = by_source.setdefault(source, {"reviews": 0, "correct": 0})
        bucket["reviews"] += 1
        bucket["correct"] += int(ok)
        reviews += 1
        correct += int(ok)

    attempts = db.execute(
        select(TacticsAttempt.attempted_at, TacticsAttempt.rating_after)
        .where(TacticsAttempt.attempted_at >= since)
        .order_by(TacticsAttempt.attempted_at, TacticsAttempt.id)
    ).all()
    in_queue = db.scalar(select(func.count(Puzzle.id)).where(Puzzle.in_queue.is_(True))) or 0
    return {
        "reviews_per_day": [{"day": day, **counts} for day, counts in sorted(per_day.items())],
        "tactics_rating": [{"at": at, "rating": rating} for at, rating in attempts],
        "by_source": by_source,
        "streak_days": streak_days(db, now),
        "totals": {"reviews": reviews, "correct": correct, "puzzles_in_queue": int(in_queue)},
    }
