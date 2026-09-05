import json
import random
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, get_setting, set_setting
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, Setting, TacticsAttempt
from chess_trainer.core.srs.queue import local_day_start
from chess_trainer.core.tactics.rating import elo_update

WIDEN_STEP = 100
MAX_WINDOW = 1200
FAILED_COOLDOWN = timedelta(days=1)
SAMPLE = 50
POINT_TRIES = 8
ID_CHUNK = 500

# RNG do módulo (e não `random` direto) para os testes poderem semear o sorteio
_rng = random.Random()


def _with_themes(q: Select, themes: Sequence[str]) -> Select:
    """Filtro de tema como EXISTS correlacionado: usa a PK composta (theme, puzzle_id)
    inteira, sem materializar as centenas de milhares de linhas de um `IN (subconsulta)`."""
    if not themes:
        return q
    return q.where(exists().where(LichessPuzzleTheme.puzzle_id == LichessPuzzle.id,
                                  LichessPuzzleTheme.theme.in_(list(themes))))


def _seen_ids(db: Session, now: datetime, exclude: Sequence[str]) -> set[str]:
    """Ids que não podem ser sorteados: já resolvidos ou tentados nas últimas 24 h, mais os excluídos.

    Carregado de uma vez porque `tactics_attempts` é pequeno (uma linha por tentativa do usuário),
    enquanto `lichess_puzzles` tem milhões: filtrar em Python evita `NOT IN (subconsulta)` no SQL,
    que fazia a seleção varrer a tabela inteira.
    """
    rows = db.scalars(select(TacticsAttempt.puzzle_id).where(
        or_(TacticsAttempt.correct.is_(True), TacticsAttempt.attempted_at > now - FAILED_COOLDOWN)))
    return set(rows) | set(exclude)


def _failed_ids(db: Session, now: datetime, seen: set[str]) -> list[str]:
    """Ids errados há mais de um dia, lidos do lado das tentativas (poucas linhas)."""
    rows = db.scalars(select(TacticsAttempt.puzzle_id).where(
        TacticsAttempt.correct.is_(False), TacticsAttempt.attempted_at <= now - FAILED_COOLDOWN).distinct())
    return [pid for pid in dict.fromkeys(rows) if pid not in seen]


def _pick_failed(db: Session, lo: int, hi: int, themes: Sequence[str], failed: list[str]) -> str | None:
    """Entre os errados antigos, sorteia um que caiba na janela e nos temas."""
    for start in range(0, len(failed), ID_CHUNK):  # lista de ids curta o bastante para o SQLite
        q = select(LichessPuzzle.id).where(LichessPuzzle.id.in_(failed[start:start + ID_CHUNK]),
                                           LichessPuzzle.rating.between(lo, hi))
        picked = db.scalar(_with_themes(q, themes).order_by(func.random()).limit(1))
        if picked is not None:
            return picked
    return None


def _pick_point(db: Session, lo: int, hi: int, themes: Sequence[str], seen: set[str]) -> str | None:
    """Sorteia um rating exato da janela e amostra só aquele ponto (poucas centenas de linhas),
    em vez de ordenar por random() a janela inteira, que tem centenas de milhares."""
    for _ in range(POINT_TRIES):
        q = select(LichessPuzzle.id).where(LichessPuzzle.rating == _rng.randint(lo, hi))
        ids = db.scalars(_with_themes(q, themes).order_by(func.random()).limit(SAMPLE)).all()
        picked = next((i for i in ids if i not in seen), None)
        if picked is not None:
            return picked
    return None


def _pick_window(db: Session, lo: int, hi: int, themes: Sequence[str], seen: set[str]) -> str | None:
    """Recurso final da janela: com tema, o sorteio é guiado pelo índice de temas
    (raros ocupam poucos pontos de rating e escapariam da amostragem por ponto)."""
    if themes:
        q = (select(LichessPuzzle.id)
             .join(LichessPuzzleTheme, LichessPuzzleTheme.puzzle_id == LichessPuzzle.id)
             .where(LichessPuzzleTheme.theme.in_(list(themes)), LichessPuzzle.rating.between(lo, hi))
             .distinct())
    else:
        q = select(LichessPuzzle.id).where(LichessPuzzle.rating.between(lo, hi))
    q = q.order_by(func.random())
    ids = db.scalars(q.limit(SAMPLE)).all()
    picked = next((i for i in ids if i not in seen), None)
    if picked is None and len(ids) == SAMPLE:
        # a amostra encheu e caiu toda em vistos: a janela ainda pode ter opção, tenta uma vez maior
        ids = db.scalars(q.limit(SAMPLE * 10)).all()
        picked = next((i for i in ids if i not in seen), None)
    return picked


def pick_next(db: Session, settings: AppSettings, now: datetime, themes: Sequence[str] = (),
              exclude: Sequence[str] = ()) -> LichessPuzzle | None:
    """Sorteia uma tática na janela de rating; errados antigos têm prioridade; alarga a janela se vazio."""
    if db.scalar(select(LichessPuzzle.id).limit(1)) is None:
        return None
    seen = _seen_ids(db, now, exclude)
    failed = _failed_ids(db, now, seen)
    window = settings.tactics_window
    while True:
        lo, hi = settings.tactics_rating - window, settings.tactics_rating + window
        picked = ((_pick_failed(db, lo, hi, themes, failed) if failed else None)
                  or _pick_point(db, lo, hi, themes, seen)
                  or _pick_window(db, lo, hi, themes, seen))
        if picked is not None:
            return db.get(LichessPuzzle, picked)
        if window >= MAX_WINDOW:
            return None
        window = min(window + WIDEN_STEP, MAX_WINDOW)


def record_attempt(db: Session, puzzle_id: str, *, correct: bool, used_hint: bool, duration_ms: int,
                   session_id: str | None, now: datetime, settings: AppSettings) -> TacticsAttempt:
    puzzle = db.get(LichessPuzzle, puzzle_id)
    if puzzle is None:
        raise KeyError(puzzle_id)
    before = int(get_setting(db, "tactics_rating", settings.tactics_rating))
    after = elo_update(before, puzzle.rating, correct and not used_hint)
    attempt = TacticsAttempt(puzzle_id=puzzle_id, session_id=session_id, attempted_at=now, correct=correct,
                             used_hint=used_hint, duration_ms=duration_ms, rating_before=before, rating_after=after,
                             puzzle_rating=puzzle.rating)
    db.add(attempt)
    # tentativa e rating novo no mesmo commit: nunca sobra uma tentativa sem o rating correspondente
    row = db.get(Setting, "tactics_rating")
    if row is None:
        db.add(Setting(key="tactics_rating", value=json.dumps(after)))
    else:
        row.value = json.dumps(after)
    db.commit()
    return attempt


def _query_theme_counts(db: Session) -> list[tuple[str, int]]:
    rows = db.execute(select(LichessPuzzleTheme.theme, func.count()).group_by(LichessPuzzleTheme.theme)
                      .order_by(func.count().desc())).all()
    return [(t, int(n)) for t, n in rows]


def theme_counts(db: Session) -> list[tuple[str, int]]:
    """Contagem por tema; usa o cache gravado na importação (o group by custa ~1 s em 3,9 M linhas)."""
    cached = get_setting(db, "lichess_theme_counts")
    if cached is not None:
        return [(str(t), int(n)) for t, n in cached]
    return _query_theme_counts(db)


def refresh_counts_cache(db: Session) -> None:
    """Grava total e contagem por tema em `settings`; chamado no fim de uma importação."""
    set_setting(db, "lichess_count", int(db.scalar(select(func.count(LichessPuzzle.id))) or 0))
    set_setting(db, "lichess_theme_counts", [[t, n] for t, n in _query_theme_counts(db)])


def tactics_status(db: Session, now: datetime) -> dict:
    cached = get_setting(db, "lichess_count")
    count = int(cached) if cached is not None else int(db.scalar(select(func.count(LichessPuzzle.id))) or 0)
    settings_rating = get_setting(db, "tactics_rating", AppSettings().tactics_rating)
    day = local_day_start(now)
    return {
        "imported": count > 0,
        "count": count,
        "imported_at": get_setting(db, "lichess_imported_at"),
        "source_rows": get_setting(db, "lichess_source_rows"),
        "rating": int(settings_rating),
        "window": int(get_setting(db, "tactics_window", AppSettings().tactics_window)),
        "attempts_total": int(db.scalar(select(func.count(TacticsAttempt.id))) or 0),
        "attempts_today": int(db.scalar(select(func.count(TacticsAttempt.id)).where(TacticsAttempt.attempted_at >= day)) or 0),
        "correct_30d": int(db.scalar(select(func.count(TacticsAttempt.id)).where(
            TacticsAttempt.attempted_at >= now - timedelta(days=30), TacticsAttempt.correct.is_(True),
            TacticsAttempt.used_hint.is_(False))) or 0),
        "attempts_30d": int(db.scalar(select(func.count(TacticsAttempt.id)).where(
            TacticsAttempt.attempted_at >= now - timedelta(days=30))) or 0),
    }
