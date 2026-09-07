import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Agora em UTC, sem tzinfo. Convenção única do projeto."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(32), default="chess.com")
    source_id: Mapped[str] = mapped_column(String(255), unique=True)
    pgn: Mapped[str] = mapped_column(Text)
    white: Mapped[str] = mapped_column(String(64))
    black: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(8))
    time_control: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(16), index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    my_color: Mapped[str] = mapped_column(String(5))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    analysis_depth: Mapped[int | None] = mapped_column(Integer, default=None)

    positions: Mapped[list["Position"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", order_by="Position.ply"
    )
    puzzles: Mapped[list["Puzzle"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    fen: Mapped[str] = mapped_column(String(100))
    move_played: Mapped[str] = mapped_column(String(10))
    move_uci: Mapped[str] = mapped_column(String(6))
    eval_before: Mapped[int] = mapped_column(Integer)
    eval_after: Mapped[int] = mapped_column(Integer)
    best_move: Mapped[str | None] = mapped_column(String(6), default=None)
    best_eval: Mapped[int] = mapped_column(Integer, default=0)
    is_mistake: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    mistake_level: Mapped[str | None] = mapped_column(String(8), default=None)
    mistake_by: Mapped[str | None] = mapped_column(String(8), default=None)

    game: Mapped[Game] = relationship(back_populates="positions")
    puzzles: Mapped[list["Puzzle"]] = relationship(back_populates="position")


class Puzzle(Base):
    """Exercício da repetição espaçada, venha de onde vier: dos erros do próprio
    usuário (`own`, com posição e partida), de uma tática guardada do Lichess
    (`lichess`) ou de um capítulo de estudo (`study`)."""

    __tablename__ = "puzzles"
    __table_args__ = (
        UniqueConstraint("fen_start", "kind", "source", name="uq_puzzle_fen_kind_source"),
        # índice nomeado (e não `unique=True` na coluna) para que o banco novo
        # e o migrado tenham o mesmo índice; no SQLite vários NULL convivem
        Index("uq_puzzle_external_id", "external_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # fora de `own` não há partida nem posição de origem
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"), index=True, default=None)
    game_id: Mapped[str | None] = mapped_column(ForeignKey("games.id"), index=True, default=None)
    source: Mapped[str] = mapped_column(String(8), default="own", index=True)
    in_queue: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(16), default=None)
    chapter_id: Mapped[str | None] = mapped_column(
        # use_alter desfaz o ciclo puzzles ↔ study_chapters na ordenação das tabelas
        ForeignKey("study_chapters.id", ondelete="SET NULL", use_alter=True), index=True, default=None
    )
    fen_before: Mapped[str | None] = mapped_column(String(100), default=None)
    last_move: Mapped[str | None] = mapped_column(String(6), default=None)
    kind: Mapped[str] = mapped_column(String(8))
    fen_start: Mapped[str] = mapped_column(String(100))
    side_to_move: Mapped[str] = mapped_column(String(5))
    solution: Mapped[str] = mapped_column(Text)
    end_reason: Mapped[str] = mapped_column(String(16))
    theme: Mapped[str] = mapped_column(String(24), index=True)
    category: Mapped[str] = mapped_column(String(16), index=True)
    solver_moves: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_leech: Mapped[bool] = mapped_column(Boolean, default=False)
    leech_since: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    srs_ease: Mapped[float] = mapped_column(Float, default=2.5)
    srs_interval_days: Mapped[int] = mapped_column(Integer, default=0)
    srs_lapses: Mapped[int] = mapped_column(Integer, default=0)
    srs_due_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    srs_last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    position: Mapped[Position | None] = relationship(back_populates="puzzles")
    game: Mapped[Game | None] = relationship(back_populates="puzzles")
    chapter: Mapped["StudyChapter | None"] = relationship(foreign_keys=[chapter_id])
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="puzzle", cascade="all, delete-orphan", order_by="Review.reviewed_at"
    )

    @property
    def solution_data(self) -> dict:
        return json.loads(self.solution)


class Study(Base):
    """Estudo do Lichess importado (ou colado como PGN)."""

    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(64), default="")
    source_url: Mapped[str] = mapped_column(String(255), default="")
    lichess_id: Mapped[str | None] = mapped_column(String(16), unique=True, default=None)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    chapters: Mapped[list["StudyChapter"]] = relationship(
        back_populates="study", cascade="all, delete-orphan", order_by="StudyChapter.order"
    )


class StudyChapter(Base):
    """Capítulo de um estudo. Em modo `gamebook` vira um puzzle; em modo `read`
    fica só como leitura (o puzzle é opcional)."""

    __tablename__ = "study_chapters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    # `order` é palavra reservada em SQL: o atributo é `order`, a coluna é `chapter_order`
    order: Mapped[int] = mapped_column("chapter_order", Integer)
    name: Mapped[str] = mapped_column(String(255))
    lichess_url: Mapped[str | None] = mapped_column(String(255), unique=True, default=None)
    fen: Mapped[str] = mapped_column(String(100), default="")
    orientation: Mapped[str] = mapped_column(String(5), default="white")
    mode: Mapped[str] = mapped_column(String(8), default="read")
    pgn: Mapped[str] = mapped_column(Text, default="")
    intro_comment: Mapped[str] = mapped_column(Text, default="")
    puzzle_id: Mapped[str | None] = mapped_column(ForeignKey("puzzles.id"), default=None)
    in_queue: Mapped[bool] = mapped_column(Boolean, default=True)

    study: Mapped[Study] = relationship(back_populates="chapters")
    puzzle: Mapped[Puzzle | None] = relationship(foreign_keys=[puzzle_id])


class TrainingSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    planned_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    filters: Mapped[str] = mapped_column(Text, default="{}")

    reviews: Mapped[list["Review"]] = relationship(back_populates="session")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("puzzles.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), default=None)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    result: Mapped[str] = mapped_column(String(8))
    used_hint: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ease: Mapped[float] = mapped_column(Float)
    interval_days: Mapped[int] = mapped_column(Integer)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    lapses: Mapped[int] = mapped_column(Integer)

    puzzle: Mapped[Puzzle] = relationship(back_populates="reviews")
    session: Mapped[TrainingSession | None] = relationship(back_populates="reviews")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON


class LichessPuzzle(Base):
    """Uma linha do banco aberto de puzzles do Lichess (CC0). `fen` é a posição
    antes do lance do adversário; `moves` (UCI, separados por espaço) começa
    com esse lance."""

    __tablename__ = "lichess_puzzles"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    fen: Mapped[str] = mapped_column(String(100))
    moves: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, index=True)
    rating_deviation: Mapped[int] = mapped_column(Integer)
    popularity: Mapped[int] = mapped_column(Integer)
    nb_plays: Mapped[int] = mapped_column(Integer)
    themes: Mapped[str] = mapped_column(Text, default="")
    opening_tags: Mapped[str] = mapped_column(Text, default="")

    @property
    def theme_list(self) -> list[str]:
        return self.themes.split()


class LichessPuzzleTheme(Base):
    __tablename__ = "lichess_puzzle_themes"

    theme: Mapped[str] = mapped_column(String(32), primary_key=True)
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("lichess_puzzles.id", ondelete="CASCADE"), primary_key=True)


class TacticsAttempt(Base):
    __tablename__ = "tactics_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("lichess_puzzles.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), default=None)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    correct: Mapped[bool] = mapped_column(Boolean)
    used_hint: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    rating_before: Mapped[int] = mapped_column(Integer)
    rating_after: Mapped[int] = mapped_column(Integer)
    puzzle_rating: Mapped[int] = mapped_column(Integer)

    puzzle: Mapped[LichessPuzzle] = relationship()
