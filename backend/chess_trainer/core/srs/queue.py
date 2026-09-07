import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from itertools import groupby

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Game, Puzzle, Review, StudyChapter

# modos de treino: repetição espaçada (só o que já foi feito e venceu), novos
# (a primeira vez dos meus erros) e estudo (um estudo inteiro, na ordem)
MODES = ("review", "new", "study")


def local_day_start(now_utc: datetime) -> datetime:
    local = now_utc.replace(tzinfo=timezone.utc).astimezone()
    midnight_naive_local = local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    # naive datetime .astimezone() é interpretado como hora local do sistema,
    # com o offset correto para aquele instante (resolve DST na meia-noite)
    return midnight_naive_local.astimezone(timezone.utc).replace(tzinfo=None)


def local_day(moment_utc: datetime) -> date:
    """Dia local de um instante gravado em UTC (as datas do banco são naive/UTC)."""
    return moment_utc.replace(tzinfo=timezone.utc).astimezone().date()


@dataclass
class QueueFilters:
    category: str | None = None
    theme: str | None = None
    kind: str | None = None
    color: str | None = None
    sources: tuple[str, ...] = ()   # vazio = todas as fontes
    study_id: str | None = None
    mode: str = "review"


@dataclass
class QueueResult:
    due: list[Puzzle]
    new: list[Puzzle]
    due_count: int
    new_available: int
    new_remaining_today: int
    # o que o modo escolhido serve, já na ordem (é isto que a API devolve)
    items: list[Puzzle] = field(default_factory=list)


def _apply_filters(stmt: Select, f: QueueFilters) -> Select:
    if f.category:
        stmt = stmt.where(Puzzle.category == f.category)
    if f.theme:
        stmt = stmt.where(Puzzle.theme == f.theme)
    if f.kind:
        stmt = stmt.where(Puzzle.kind == f.kind)
    if f.color:
        stmt = stmt.where(Puzzle.side_to_move == f.color)
    if f.sources:
        stmt = stmt.where(Puzzle.source.in_(f.sources))
    if f.study_id:
        stmt = stmt.where(
            Puzzle.chapter_id.in_(select(StudyChapter.id).where(StudyChapter.study_id == f.study_id))
        )
    return stmt


def count_new_reviewed_today(db: Session, now: datetime) -> int:
    """Quantos exercícios tiveram a primeira revisão hoje, contando só os erros do
    próprio usuário: é o que desconta do limite diário de "novos" (táticas e
    estudos entram na repetição pela tela deles, sem passar por "novos")."""
    day_start = local_day_start(now)
    first_reviews = (
        select(Review.puzzle_id, func.min(Review.reviewed_at).label("first_at"))
        .group_by(Review.puzzle_id)
        .subquery()
    )
    stmt = (
        select(func.count())
        .select_from(first_reviews)
        .join(Puzzle, Puzzle.id == first_reviews.c.puzzle_id)
        .where(first_reviews.c.first_at >= day_start, Puzzle.source == "own")
    )
    return int(db.scalar(stmt) or 0)


def _shuffle_within_days(due: list[Puzzle], rng: random.Random) -> list[Puzzle]:
    """Mantém os dias de vencimento em ordem (o mais atrasado primeiro) e
    embaralha os exercícios de um mesmo dia, para não repetir sempre a mesma
    sequência. A lista chega ordenada por `srs_due_at`."""
    ordenados: list[Puzzle] = []
    for _, do_dia in groupby(due, key=lambda p: local_day(p.srs_due_at)):
        bloco = list(do_dia)
        rng.shuffle(bloco)
        ordenados.extend(bloco)
    return ordenados


def build_queue(db: Session, filters: QueueFilters, settings: AppSettings, now: datetime,
                rng: random.Random | None = None) -> QueueResult:
    if filters.mode not in MODES:
        raise ValueError(f"modo inválido: {filters.mode}")
    if filters.mode == "study" and not filters.study_id:
        raise ValueError("informe o estudo para treinar")
    rng = rng or random.Random()
    # fora da fila (in_queue = false) o puzzle e seu histórico ficam, mas ele não é servido nem contado
    base = _apply_filters(select(Puzzle).where(Puzzle.is_leech.is_(False), Puzzle.in_queue.is_(True)), filters)
    # `srs_due_at <= now` já exclui os nulos (nunca revisados): em SQL, NULL <= x não é verdadeiro
    due_stmt = base.where(Puzzle.srs_due_at <= now)

    nunca_revisados = base.where(Puzzle.srs_due_at.is_(None))
    # "novos" são os erros do próprio usuário; no modo estudo, os exercícios do estudo ainda não feitos
    if filters.mode != "study":
        nunca_revisados = nunca_revisados.where(Puzzle.source == "own")
    new_available = int(db.scalar(select(func.count()).select_from(nunca_revisados.subquery())) or 0)
    remaining = max(0, settings.new_per_day - count_new_reviewed_today(db, now))

    due: list[Puzzle] = []
    new: list[Puzzle] = []
    items: list[Puzzle] = []

    if filters.mode == "study":
        # o estudo inteiro na ordem dos capítulos, feito ou não, sem limite diário
        items = list(db.scalars(
            base.join(StudyChapter, StudyChapter.id == Puzzle.chapter_id)
                .order_by(StudyChapter.order, Puzzle.id)
        ).all())
        due = [p for p in items if p.srs_due_at is not None and p.srs_due_at <= now]
        new = [p for p in items if p.srs_due_at is None]
        due_count = len(due)
    elif filters.mode == "new":
        due_count = int(db.scalar(select(func.count()).select_from(due_stmt.subquery())) or 0)
        if remaining > 0:
            new = _pick_new(db, nunca_revisados, settings, remaining, rng)
        items = new
    else:
        due = _shuffle_within_days(list(db.scalars(due_stmt.order_by(Puzzle.srs_due_at)).all()), rng)
        due_count = len(due)
        items = due

    return QueueResult(due=due, new=new, due_count=due_count,
                       new_available=new_available, new_remaining_today=remaining, items=items)


def _pick_new(db: Session, stmt: Select, settings: AppSettings, limit: int, rng: random.Random) -> list[Puzzle]:
    if settings.new_order == "recent":
        # puzzles de fora das partidas do usuário não têm `game`: a data deles é a de criação
        recentes = (stmt.outerjoin(Game, Game.id == Puzzle.game_id)
                    .order_by(func.coalesce(Game.played_at, Puzzle.created_at).desc()))
        return list(db.scalars(recentes.limit(limit)).all())
    sorteio = list(db.scalars(stmt).all())
    rng.shuffle(sorteio)
    return sorteio[:limit]
