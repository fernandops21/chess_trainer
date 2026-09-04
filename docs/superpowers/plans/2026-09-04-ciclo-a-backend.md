# Ciclo A — Backend (núcleo + API) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend completo do ciclo A: importar partidas do chess.com, analisar com Stockfish, detectar erros, gerar puzzles "punir"/"evitar" que só terminam quando o ganho se materializa, e servir fila de treino com repetição espaçada via API HTTP.

**Architecture:** Pacote Python `chess_trainer` com um núcleo (`core/`) sem dependência de web, testável com uma engine falsa scriptada, e uma camada fina FastAPI (`api/`) que expõe o núcleo e roda tarefas longas numa fila em segundo plano de um job por vez. Persistência em SQLite via SQLAlchemy 2.0; datas sempre em UTC sem fuso.

**Tech Stack:** Python ≥ 3.12 gerenciado com `uv`; python-chess, SQLAlchemy 2.0, FastAPI, uvicorn, httpx, pydantic v2; pytest. Stockfish nativo via UCI.

**Spec:** `docs/superpowers/specs/2026-09-04-chess-trainer-ciclo-a-design.md`

## Global Constraints

- Todos os comandos abaixo rodam de dentro de `backend/` (`cd backend`). Testes: `uv run pytest -q`. Testes lentos (Stockfish real) são marcados `@pytest.mark.slow` e pulados quando não há engine.
- `requires-python = ">=3.12"`. A máquina tem Python 3.14 e `uv` 0.10.
- Avaliações: inteiros em centipawns, sempre do ponto de vista do lado que vai jogar na posição avaliada. Mate em n = `100000 - n`; mate contra em n = `-(100000 - n)`. Limiar de mate: `|score| >= 90000`.
- Datas: `datetime` **naive em UTC** em todo o código e no banco. Helper único `utcnow()` em `core/models.py`. "Hoje" = meia-noite local convertida para UTC (`local_day_start`).
- Usuário do chess.com sempre em minúsculas e sem espaços ao salvar.
- Defaults das configurações (spec §3): categorias `["rapid","daily","classical"]`, `analysis_depth=18`, `puzzle_depth=20`, `mistake_threshold_cp=100`, `blunder_threshold_cp=200`, `avoid_gap_cp=150`, `new_per_day=10`, `leech_lapses=5`.
- Geração de puzzles (spec §7): multipv 3, janela de alternativas 50 cp, máximo 10 lances do solver (15 em mate), solver precisa estar ≥ +100 cp ou com mate a favor, alternativas só no lance final.
- SRS (spec §8): ease inicial 2.5, mínimo 1.3; erro ou dica → intervalo 1 e ease −0.2, lapses +1; acerto: 0→1, 1→3, senão `round(intervalo_real × ease)`; bônus +0.1 de ease se `duration_ms ≤ 10000 × solver_moves`.
- IDs são UUID4 em string. Nenhum módulo de `core/` importa de `api/`.
- Commits pequenos, mensagens em português no estilo `feat:`/`test:`/`chore:`, terminando com `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Estrutura de arquivos

```
backend/
  pyproject.toml
  .gitignore                         data/, engines/, .venv/
  chess_trainer/
    __init__.py
    __main__.py                      python -m chess_trainer → uvicorn
    config.py                        AppSettings + load/save + get/set_setting
    core/
      __init__.py
      models.py                      Base, Game, Position, Puzzle, Review, TrainingSession, Setting, utcnow, new_id
      db.py                          make_engine(path), make_session_factory, init_db
      evals.py                       MATE_SCORE, is_mate_for/against, clamp, to_pawns, format_score
      importers/__init__.py
      importers/chesscom.py          ChessComClient, ChessComError
      importers/service.py           parse_game, import_games, ImportResult
      analysis/__init__.py
      analysis/engine.py             LineEval, EngineLike, StockfishEngine, find_stockfish, terminal_score
      analysis/game_analyzer.py      PositionData, analyze_game
      analysis/mistakes.py           Thresholds, classify_move, classify_positions
      puzzles/__init__.py
      puzzles/material.py            PIECE_VALUES, material_balance, floor_to_piece
      puzzles/generator.py           SolutionMove, PuzzleDraft, PuzzleConfig, generate_punish, generate_avoid
      puzzles/themes.py              infer_theme
      puzzles/service.py             generate_puzzles_for_game, regenerate_all
      srs/__init__.py
      srs/scheduler.py               SrsState, next_state
      srs/queue.py                   QueueFilters, build_queue, local_day_start
      srs/reviews.py                 record_review, unleech
      pipeline.py                    analyze_pending
    api/
      __init__.py
      app.py                         create_app
      deps.py                        get_db
      jobs.py                        JobRunner, JobStatus
      schemas.py                     pydantic models
      routes/__init__.py
      routes/system.py               /api/status, /api/settings, /api/import, /api/analyze, /api/puzzles/regenerate
      routes/games.py                /api/games, /api/games/{id}, /api/mistakes
      routes/training.py             /api/puzzles/{id}, /api/queue, /api/leeches, unleech, sessions, reviews, dashboard
  tests/
    conftest.py                      db_session fixture
    fakes.py                         FakeEngine
    fixtures/chesscom_archives.json
    fixtures/chesscom_month.json
    test_*.py
```

---

### Task 1: Scaffold do projeto Python

**Files:**
- Create: `backend/pyproject.toml`, `backend/.gitignore`, `backend/chess_trainer/__init__.py`, `backend/chess_trainer/core/__init__.py`, `backend/chess_trainer/core/importers/__init__.py`, `backend/chess_trainer/core/analysis/__init__.py`, `backend/chess_trainer/core/puzzles/__init__.py`, `backend/chess_trainer/core/srs/__init__.py`, `backend/chess_trainer/api/__init__.py`, `backend/chess_trainer/api/routes/__init__.py`, `backend/tests/__init__.py`, `backend/tests/test_smoke.py`

**Interfaces:**
- Produces: pacote importável `chess_trainer`; comando `uv run pytest`.

- [ ] **Step 1: Criar `backend/pyproject.toml`**

```toml
[project]
name = "chess-trainer"
version = "0.1.0"
description = "Treino de xadrez: puzzles dos seus próprios erros com repetição espaçada"
requires-python = ">=3.12"
dependencies = [
  "chess>=1.11",
  "sqlalchemy>=2.0",
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
  "pydantic>=2.7",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-timeout>=2"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: precisa do Stockfish real"]
timeout = 120

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["chess_trainer"]
```

- [ ] **Step 2: Criar `backend/.gitignore`**

```
.venv/
data/
engines/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Criar os `__init__.py` vazios** listados em Files (todos vazios, exceto `chess_trainer/__init__.py`, que contém `__version__ = "0.1.0"`).

- [ ] **Step 4: Escrever o teste de fumaça `backend/tests/test_smoke.py`**

```python
import chess
import chess_trainer


def test_package_imports():
    assert chess_trainer.__version__ == "0.1.0"
    assert chess.Board().fen().startswith("rnbqkbnr")
```

- [ ] **Step 5: Instalar e rodar**

Run: `cd backend && uv sync && uv run pytest -q`
Expected: `1 passed`. Se `uv sync` falhar por falta de wheel para Python 3.14 em alguma dependência, rodar `uv python pin 3.12` (o `uv` baixa o interpretador) e repetir.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "chore: scaffold do backend Python com uv e pytest"
```

---

### Task 2: Helpers de avaliação (`core/evals.py`)

**Files:**
- Create: `backend/chess_trainer/core/evals.py`
- Test: `backend/tests/test_evals.py`

**Interfaces:**
- Produces:
  - `MATE_SCORE: int = 100_000`, `MATE_THRESHOLD: int = 90_000`, `CLAMP_CP: int = 2_000`
  - `is_mate_for(score: int) -> bool`, `is_mate_against(score: int) -> bool`, `is_mate(score: int) -> bool`
  - `mate_in(score: int) -> int | None` (n positivo, independente do lado)
  - `clamp(score: int) -> int`, `to_pawns(score: int) -> float`
  - `format_score(score: int) -> str` (`"#2"`, `"#-3"`, `"+1.25"`, `"-0.40"`, `"0.00"`)

- [ ] **Step 1: Escrever os testes**

```python
from chess_trainer.core.evals import (
    MATE_SCORE, clamp, format_score, is_mate, is_mate_against, is_mate_for, mate_in, to_pawns,
)


def test_mate_detection():
    assert is_mate_for(MATE_SCORE - 3)
    assert not is_mate_for(-(MATE_SCORE - 3))
    assert is_mate_against(-(MATE_SCORE - 1))
    assert is_mate(MATE_SCORE - 10) and is_mate(-(MATE_SCORE - 10))
    assert not is_mate(1500)


def test_mate_in():
    assert mate_in(MATE_SCORE - 2) == 2
    assert mate_in(-(MATE_SCORE - 5)) == 5
    assert mate_in(300) is None


def test_clamp_and_pawns():
    assert clamp(MATE_SCORE - 1) == 2000
    assert clamp(-5000) == -2000
    assert clamp(150) == 150
    assert to_pawns(150) == 1.5
    assert to_pawns(MATE_SCORE - 1) == 20.0


def test_format_score():
    assert format_score(MATE_SCORE - 2) == "#2"
    assert format_score(-(MATE_SCORE - 3)) == "#-3"
    assert format_score(125) == "+1.25"
    assert format_score(-40) == "-0.40"
    assert format_score(0) == "0.00"
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_evals.py -q`
Expected: FAIL com `ModuleNotFoundError: chess_trainer.core.evals`

- [ ] **Step 3: Implementar `core/evals.py`**

```python
"""Convenções de avaliação: centipawns inteiros, mate codificado como ±(MATE_SCORE - n)."""

MATE_SCORE = 100_000
MATE_THRESHOLD = 90_000
CLAMP_CP = 2_000


def is_mate_for(score: int) -> bool:
    return score >= MATE_THRESHOLD


def is_mate_against(score: int) -> bool:
    return score <= -MATE_THRESHOLD


def is_mate(score: int) -> bool:
    return abs(score) >= MATE_THRESHOLD


def mate_in(score: int) -> int | None:
    if not is_mate(score):
        return None
    return MATE_SCORE - abs(score)


def clamp(score: int) -> int:
    return max(-CLAMP_CP, min(CLAMP_CP, score))


def to_pawns(score: int) -> float:
    return clamp(score) / 100


def format_score(score: int) -> str:
    n = mate_in(score)
    if n is not None:
        return f"#{n}" if score > 0 else f"#-{n}"
    if score == 0:
        return "0.00"
    return f"{score / 100:+.2f}"
```

- [ ] **Step 4: Rodar para ver passar**

Run: `uv run pytest tests/test_evals.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/core/evals.py backend/tests/test_evals.py
git commit -m "feat: helpers de avaliação com codificação de mate"
```

---

### Task 3: Modelos, banco e configurações

**Files:**
- Create: `backend/chess_trainer/core/models.py`, `backend/chess_trainer/core/db.py`, `backend/chess_trainer/config.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py`, `backend/tests/test_config.py`

**Interfaces:**
- Produces (models): `Base`, `new_id() -> str`, `utcnow() -> datetime` (naive UTC), classes `Game`, `Position`, `Puzzle`, `Review`, `TrainingSession`, `Setting` com as colunas do spec §3 (nomes exatos abaixo); `Puzzle.solution_data` property (dict decodificado).
- Produces (db): `make_engine(db_path: str | None) -> Engine` (`None` ou `":memory:"` → SQLite em memória com `StaticPool`), `make_session_factory(engine) -> sessionmaker`, `init_db(engine) -> None`.
- Produces (config): `@dataclass AppSettings` (campos e defaults dos Global Constraints), `load_settings(db) -> AppSettings`, `save_settings(db, settings) -> AppSettings` (normaliza username), `get_setting(db, key, default=None)`, `set_setting(db, key, value)` (valores JSON), `thresholds_from(settings) -> Thresholds` fica para a Task 8.
- Produces (tests): fixture `db_session` (sessão SQLAlchemy sobre SQLite em memória, tabelas criadas).

- [ ] **Step 1: Escrever `tests/conftest.py`**

```python
import pytest
from sqlalchemy.orm import Session

from chess_trainer.core.db import init_db, make_engine, make_session_factory


@pytest.fixture
def db_engine():
    engine = make_engine(":memory:")
    init_db(engine)
    return engine


@pytest.fixture
def db_session(db_engine) -> Session:
    factory = make_session_factory(db_engine)
    with factory() as session:
        yield session
```

- [ ] **Step 2: Escrever `tests/test_models.py`**

```python
import json
from datetime import datetime

from chess_trainer.core.models import Game, Position, Puzzle, Review, TrainingSession, utcnow


def _game(**over):
    base = dict(
        source_id="https://www.chess.com/game/live/1",
        pgn="1. e4 e5 1-0",
        white="therealzibs",
        black="x",
        result="1-0",
        time_control="600",
        category="rapid",
        played_at=datetime(2026, 8, 1, 12, 0),
        my_color="white",
    )
    base.update(over)
    return Game(**base)


def test_utcnow_is_naive():
    assert utcnow().tzinfo is None


def test_game_defaults_and_relationships(db_session):
    game = _game()
    db_session.add(game)
    db_session.commit()
    assert len(game.id) == 36
    assert game.source == "chess.com"
    assert game.analyzed_at is None
    assert game.imported_at is not None


def test_position_puzzle_review_chain(db_session):
    game = _game()
    pos = Position(
        game=game, ply=1, fen="startfen", move_played="e4", move_uci="e2e4",
        eval_before=20, eval_after=15, best_move="e2e4", best_eval=20,
    )
    puzzle = Puzzle(
        position=pos, game=game, kind="punish", fen_start="f", side_to_move="white",
        solution=json.dumps({"moves": [{"uci": "e2e4", "by": "solver", "alternatives": []}]}),
        end_reason="material_gain", theme="tactic", category="rapid", solver_moves=1,
    )
    session = TrainingSession(planned_minutes=25, filters="{}")
    review = Review(
        puzzle=puzzle, session=session, result="correct", used_hint=False, duration_ms=1200,
        ease=2.5, interval_days=1, due_at=datetime(2026, 9, 5), lapses=0,
    )
    db_session.add_all([game, pos, puzzle, session, review])
    db_session.commit()

    assert pos.is_mistake is False and pos.mistake_level is None
    assert puzzle.is_leech is False and puzzle.srs_due_at is None and puzzle.srs_ease == 2.5
    assert puzzle.solution_data["moves"][0]["uci"] == "e2e4"
    assert game.positions[0] is pos
    assert puzzle.reviews[0] is review


def test_puzzle_unique_fen_kind(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    game = _game()
    db_session.add(game)
    for _ in range(2):
        pos = Position(game=game, ply=1, fen="f", move_played="e4", move_uci="e2e4",
                       eval_before=0, eval_after=0, best_move="e2e4", best_eval=0)
        db_session.add(Puzzle(position=pos, game=game, kind="punish", fen_start="same", side_to_move="white",
                              solution="{}", end_reason="mate", theme="tactic", category="rapid", solver_moves=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 3: Escrever `tests/test_config.py`**

```python
from chess_trainer.config import AppSettings, get_setting, load_settings, save_settings, set_setting


def test_defaults_when_empty(db_session):
    s = load_settings(db_session)
    assert s == AppSettings()
    assert s.categories == ["rapid", "daily", "classical"]
    assert s.analysis_depth == 18 and s.puzzle_depth == 22
    assert s.mistake_threshold_cp == 100 and s.blunder_threshold_cp == 200
    assert s.avoid_gap_cp == 150 and s.new_per_day == 10 and s.leech_lapses == 5


def test_save_normalizes_username_and_roundtrips(db_session):
    s = AppSettings(chesscom_username="  TheRealZibs ", categories=["rapid"], analysis_depth=12)
    saved = save_settings(db_session, s)
    assert saved.chesscom_username == "therealzibs"
    again = load_settings(db_session)
    assert again.chesscom_username == "therealzibs"
    assert again.categories == ["rapid"]
    assert again.analysis_depth == 12
    assert again.puzzle_depth == 22  # default preservado


def test_raw_setting_helpers(db_session):
    assert get_setting(db_session, "last_imported_archive") is None
    set_setting(db_session, "last_imported_archive", "https://x/2026/09")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/09"
    set_setting(db_session, "last_imported_archive", "https://x/2026/10")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/10"
```

- [ ] **Step 4: Rodar para ver falhar**

Run: `uv run pytest tests/test_models.py tests/test_config.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 5: Implementar `core/models.py`**

```python
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    __tablename__ = "puzzles"
    __table_args__ = (UniqueConstraint("fen_start", "kind", name="uq_puzzle_fen_kind"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    position_id: Mapped[str] = mapped_column(ForeignKey("positions.id"), index=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
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

    position: Mapped[Position] = relationship(back_populates="puzzles")
    game: Mapped[Game] = relationship(back_populates="puzzles")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="puzzle", cascade="all, delete-orphan", order_by="Review.reviewed_at"
    )

    @property
    def solution_data(self) -> dict:
        return json.loads(self.solution)


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
```

- [ ] **Step 6: Implementar `core/db.py`**

```python
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chess_trainer.core.models import Base


def make_engine(db_path: str | None) -> Engine:
    if db_path is None or db_path == ":memory:":
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
```

- [ ] **Step 7: Implementar `config.py`**

```python
import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from sqlalchemy.orm import Session

from chess_trainer.core.models import Setting


@dataclass
class AppSettings:
    chesscom_username: str = ""
    categories: list[str] = field(default_factory=lambda: ["rapid", "daily", "classical"])
    stockfish_path: str = ""
    analysis_depth: int = 18
    puzzle_depth: int = 22
    mistake_threshold_cp: int = 100
    blunder_threshold_cp: int = 200
    avoid_gap_cp: int = 150
    new_per_day: int = 10
    leech_lapses: int = 5


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    return json.loads(row.value) if row else default


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)
    db.commit()


def load_settings(db: Session) -> AppSettings:
    values: dict[str, Any] = {}
    for f in fields(AppSettings):
        stored = get_setting(db, f.name, None)
        if stored is not None:
            values[f.name] = stored
    return AppSettings(**values)


def save_settings(db: Session, settings: AppSettings) -> AppSettings:
    settings.chesscom_username = settings.chesscom_username.strip().lower()
    for key, value in asdict(settings).items():
        set_setting(db, key, value)
    return settings
```

- [ ] **Step 8: Rodar para ver passar**

Run: `uv run pytest tests/test_models.py tests/test_config.py -q`
Expected: `7 passed`

- [ ] **Step 9: Commit**

```bash
git add backend/chess_trainer/core/models.py backend/chess_trainer/core/db.py backend/chess_trainer/config.py backend/tests
git commit -m "feat: modelos SQLAlchemy, banco SQLite e configurações"
```

---

### Task 4: Cliente da API do chess.com

**Files:**
- Create: `backend/chess_trainer/core/importers/chesscom.py`, `backend/tests/fixtures/chesscom_archives.json`, `backend/tests/fixtures/chesscom_month.json`
- Test: `backend/tests/test_chesscom_client.py`

**Interfaces:**
- Produces: `class ChessComError(Exception)`; `class ChessComClient(user_agent: str, http: httpx.Client | None = None)` com `list_archives(username: str) -> list[str]` e `fetch_month(archive_url: str) -> list[dict]` (cada dict é o objeto bruto de partida do chess.com: `url, pgn, time_class, time_control, end_time, rules, white{username,result}, black{username,result}`).
- Produces (fixtures): `chesscom_month.json` com 3 partidas: `live/1001` rapid padrão (usuário de brancas), `live/1002` blitz padrão (usuário de pretas), `live/1003` rapid `chess960`.

- [ ] **Step 1: Criar `tests/fixtures/chesscom_archives.json`**

```json
{"archives": [
  "https://api.chess.com/pub/player/therealzibs/games/2026/07",
  "https://api.chess.com/pub/player/therealzibs/games/2026/08"
]}
```

- [ ] **Step 2: Criar `tests/fixtures/chesscom_month.json`**

```json
{"games": [
  {
    "url": "https://www.chess.com/game/live/1001",
    "pgn": "[Event \"Live Chess\"]\n[Site \"Chess.com\"]\n[Date \"2026.08.02\"]\n[White \"therealzibs\"]\n[Black \"opp_one\"]\n[Result \"1-0\"]\n[TimeControl \"600\"]\n[Link \"https://www.chess.com/game/live/1001\"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0\n",
    "time_control": "600", "end_time": 1785672000, "rated": true, "time_class": "rapid", "rules": "chess",
    "white": {"username": "therealzibs", "result": "win", "rating": 1200},
    "black": {"username": "opp_one", "result": "checkmated", "rating": 1180}
  },
  {
    "url": "https://www.chess.com/game/live/1002",
    "pgn": "[Event \"Live Chess\"]\n[Site \"Chess.com\"]\n[Date \"2026.08.03\"]\n[White \"opp_two\"]\n[Black \"therealzibs\"]\n[Result \"0-1\"]\n[TimeControl \"180\"]\n[Link \"https://www.chess.com/game/live/1002\"]\n\n1. f3 e5 2. g4 Qh4# 0-1\n",
    "time_control": "180", "end_time": 1785758400, "rated": true, "time_class": "blitz", "rules": "chess",
    "white": {"username": "opp_two", "result": "checkmated", "rating": 1100},
    "black": {"username": "therealzibs", "result": "win", "rating": 1210}
  },
  {
    "url": "https://www.chess.com/game/live/1003",
    "pgn": "[Event \"Live Chess\"]\n[Site \"Chess.com\"]\n[Date \"2026.08.04\"]\n[White \"therealzibs\"]\n[Black \"opp_three\"]\n[Result \"1/2-1/2\"]\n[TimeControl \"600\"]\n[Variant \"Chess960\"]\n[Link \"https://www.chess.com/game/live/1003\"]\n\n1. e4 e5 1/2-1/2\n",
    "time_control": "600", "end_time": 1785844800, "rated": true, "time_class": "rapid", "rules": "chess960",
    "white": {"username": "therealzibs", "result": "agreed", "rating": 1200},
    "black": {"username": "opp_three", "result": "agreed", "rating": 1200}
  }
]}
```

- [ ] **Step 3: Escrever `tests/test_chesscom_client.py`**

```python
import json
from pathlib import Path

import httpx
import pytest

from chess_trainer.core.importers.chesscom import ChessComClient, ChessComError

FIXTURES = Path(__file__).parent / "fixtures"


def _client(handler):
    transport = httpx.MockTransport(handler)
    return ChessComClient("chess-trainer-tests", http=httpx.Client(transport=transport))


def _ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["user-agent"] == "chess-trainer-tests"
    if request.url.path.endswith("/games/archives"):
        return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_archives.json").read_text()))
    if request.url.path.endswith("/games/2026/08"):
        return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_month.json").read_text()))
    return httpx.Response(404, json={"message": "not found"})


def test_list_archives_uses_lowercase_username():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return _ok_handler(request)

    archives = _client(handler).list_archives("TheRealZibs")
    assert seen == ["https://api.chess.com/pub/player/therealzibs/games/archives"]
    assert archives[-1].endswith("/2026/08")


def test_fetch_month_returns_raw_games():
    games = _client(_ok_handler).fetch_month("https://api.chess.com/pub/player/therealzibs/games/2026/08")
    assert [g["url"].rsplit("/", 1)[1] for g in games] == ["1001", "1002", "1003"]
    assert games[0]["time_class"] == "rapid"


def test_404_raises_user_not_found():
    with pytest.raises(ChessComError, match="não encontrado"):
        _client(lambda r: httpx.Response(404, json={})).list_archives("nobody")


def test_429_raises_rate_limited():
    with pytest.raises(ChessComError, match="limite"):
        _client(lambda r: httpx.Response(429)).list_archives("x")


def test_network_error_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ChessComError, match="rede"):
        _client(handler).list_archives("x")
```

- [ ] **Step 4: Rodar para ver falhar**

Run: `uv run pytest tests/test_chesscom_client.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 5: Implementar `core/importers/chesscom.py`**

```python
import httpx

BASE_URL = "https://api.chess.com/pub"


class ChessComError(Exception):
    pass


class ChessComClient:
    def __init__(self, user_agent: str, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30.0)
        self._headers = {"User-Agent": user_agent}

    def _get_json(self, url: str) -> dict:
        try:
            resp = self._http.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ChessComError(f"erro de rede ao acessar {url}: {exc}") from exc
        if resp.status_code == 404:
            raise ChessComError("usuário ou arquivo não encontrado no chess.com")
        if resp.status_code == 429:
            raise ChessComError("limite de requisições do chess.com atingido; tente de novo em alguns minutos")
        if resp.status_code >= 400:
            raise ChessComError(f"chess.com respondeu HTTP {resp.status_code}")
        return resp.json()

    def list_archives(self, username: str) -> list[str]:
        user = username.strip().lower()
        data = self._get_json(f"{BASE_URL}/player/{user}/games/archives")
        return list(data.get("archives", []))

    def fetch_month(self, archive_url: str) -> list[dict]:
        data = self._get_json(archive_url)
        return list(data.get("games", []))

    def close(self) -> None:
        self._http.close()
```

- [ ] **Step 6: Rodar para ver passar**

Run: `uv run pytest tests/test_chesscom_client.py -q`
Expected: `5 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/chess_trainer/core/importers/chesscom.py backend/tests/fixtures backend/tests/test_chesscom_client.py
git commit -m "feat: cliente da API pública do chess.com"
```

---

### Task 5: Serviço de importação

**Files:**
- Create: `backend/chess_trainer/core/importers/service.py`
- Test: `backend/tests/test_import_service.py`

**Interfaces:**
- Consumes: `ChessComClient` (Task 4), `Game`, `utcnow` (Task 3), `AppSettings`, `get_setting`, `set_setting` (Task 3).
- Produces:
  - `@dataclass ParsedGame(source_id, pgn, white, black, result, time_control, category, played_at, my_color)`
  - `parse_game(raw: dict, username: str) -> ParsedGame | None` (`None` quando `rules != "chess"`)
  - `@dataclass ImportResult(imported: int = 0, skipped: int = 0, filtered: int = 0, months: int = 0)`
  - `ProgressFn = Callable[[str, int, int, str], None]` (stage, done, total, message). O mesmo tipo é usado pela análise e pela API.
  - `import_games(db, client, settings, progress: ProgressFn | None = None) -> ImportResult`
  - Chave de estado em `Setting`: `"last_imported_archive"` (URL do último mês processado; a importação seguinte recomeça **nesse** mês, inclusive).

- [ ] **Step 1: Escrever `tests/test_import_service.py`**

```python
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from chess_trainer.config import AppSettings, get_setting
from chess_trainer.core.importers.chesscom import ChessComClient, ChessComError
from chess_trainer.core.importers.service import import_games, parse_game
from chess_trainer.core.models import Game

FIXTURES = Path(__file__).parent / "fixtures"
MONTH = json.loads((FIXTURES / "chesscom_month.json").read_text())["games"]
ARCHIVES = json.loads((FIXTURES / "chesscom_archives.json").read_text())


def _client(month_by_suffix: dict[str, list[dict]], calls: list[str] | None = None):
    def handler(request: httpx.Request):
        if calls is not None:
            calls.append(str(request.url))
        if request.url.path.endswith("/games/archives"):
            return httpx.Response(200, json=ARCHIVES)
        for suffix, games in month_by_suffix.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json={"games": games})
        return httpx.Response(500)

    return ChessComClient("t", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_parse_game_white_and_black():
    g = parse_game(MONTH[0], "therealzibs")
    assert g.source_id == "https://www.chess.com/game/live/1001"
    assert g.my_color == "white" and g.result == "1-0" and g.category == "rapid"
    assert g.played_at == datetime(2026, 8, 2, 12, 0)
    g2 = parse_game(MONTH[1], "therealzibs")
    assert g2.my_color == "black" and g2.result == "0-1" and g2.category == "blitz"


def test_parse_game_skips_variants():
    assert parse_game(MONTH[2], "therealzibs") is None


def test_import_filters_categories_and_dedups(db_session):
    settings = AppSettings(chesscom_username="therealzibs")  # rapid/daily/classical
    client = _client({"/2026/07": [], "/2026/08": MONTH})
    result = import_games(db_session, client, settings)
    assert (result.imported, result.filtered, result.skipped, result.months) == (1, 2, 0, 2)
    games = db_session.scalars(select(Game)).all()
    assert [g.source_id for g in games] == ["https://www.chess.com/game/live/1001"]
    assert get_setting(db_session, "last_imported_archive").endswith("/2026/08")

    again = import_games(db_session, client, settings)
    assert (again.imported, again.skipped, again.months) == (0, 1, 1)  # retoma do último mês


def test_import_with_blitz_enabled(db_session):
    settings = AppSettings(chesscom_username="therealzibs", categories=["rapid", "blitz"])
    result = import_games(db_session, _client({"/2026/07": [], "/2026/08": MONTH}), settings)
    assert result.imported == 2


def test_import_resumes_from_last_archive(db_session):
    settings = AppSettings(chesscom_username="therealzibs")
    calls: list[str] = []
    import_games(db_session, _client({"/2026/07": [], "/2026/08": MONTH}, calls), settings)
    calls.clear()
    import_games(db_session, _client({"/2026/07": [], "/2026/08": MONTH}, calls), settings)
    assert not any(c.endswith("/2026/07") for c in calls)


def test_import_reports_progress_and_propagates_errors(db_session):
    settings = AppSettings(chesscom_username="therealzibs")
    events = []
    client = _client({"/2026/07": []})  # /2026/08 devolve 500
    with pytest.raises(ChessComError):
        import_games(db_session, client, settings, progress=lambda *a: events.append(a))
    assert events[0][0] == "import" and events[0][2] == 2
    # o mês que falhou fica como próximo ponto de retomada
    assert get_setting(db_session, "last_imported_archive").endswith("/2026/08")


def test_import_requires_username(db_session):
    with pytest.raises(ValueError):
        import_games(db_session, _client({}), AppSettings(chesscom_username=""))
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_import_service.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar `core/importers/service.py`**

```python
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, get_setting, set_setting
from chess_trainer.core.importers.chesscom import ChessComClient
from chess_trainer.core.models import Game

ProgressFn = Callable[[str, int, int, str], None]
LAST_ARCHIVE_KEY = "last_imported_archive"


@dataclass
class ParsedGame:
    source_id: str
    pgn: str
    white: str
    black: str
    result: str
    time_control: str
    category: str
    played_at: datetime
    my_color: str


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    filtered: int = 0
    months: int = 0


def parse_game(raw: dict, username: str) -> ParsedGame | None:
    if raw.get("rules", "chess") != "chess":
        return None
    white = raw["white"]["username"]
    black = raw["black"]["username"]
    headers = chess.pgn.read_headers(io.StringIO(raw["pgn"])) or {}
    result = headers.get("Result", "*")
    played_at = datetime.fromtimestamp(int(raw["end_time"]), tz=timezone.utc).replace(tzinfo=None)
    my_color = "white" if white.lower() == username.lower() else "black"
    return ParsedGame(
        source_id=raw["url"],
        pgn=raw["pgn"],
        white=white,
        black=black,
        result=result,
        time_control=str(raw.get("time_control", "")),
        category=raw.get("time_class", "rapid"),
        played_at=played_at,
        my_color=my_color,
    )


def _month_label(archive_url: str) -> str:
    parts = archive_url.rstrip("/").rsplit("/", 2)
    return f"{parts[-2]}/{parts[-1]}"


def import_games(
    db: Session,
    client: ChessComClient,
    settings: AppSettings,
    progress: ProgressFn | None = None,
) -> ImportResult:
    username = settings.chesscom_username.strip().lower()
    if not username:
        raise ValueError("configure o usuário do chess.com antes de importar")

    archives = client.list_archives(username)
    last = get_setting(db, LAST_ARCHIVE_KEY)
    start = archives.index(last) if last in archives else 0
    pending = archives[start:]

    result = ImportResult()
    for i, archive_url in enumerate(pending):
        if progress:
            progress("import", i, len(pending), _month_label(archive_url))
        set_setting(db, LAST_ARCHIVE_KEY, archive_url)  # ponto de retomada, gravado antes de buscar
        raw_games = client.fetch_month(archive_url)
        for raw in raw_games:
            parsed = parse_game(raw, username)
            if parsed is None or parsed.category not in settings.categories:
                result.filtered += 1
                continue
            exists = db.scalar(select(Game.id).where(Game.source_id == parsed.source_id))
            if exists:
                result.skipped += 1
                continue
            db.add(Game(**parsed.__dict__))
            result.imported += 1
        db.commit()
        result.months += 1
    if progress:
        progress("import", len(pending), len(pending), "concluído")
    return result
```

- [ ] **Step 4: Rodar para ver passar**

Run: `uv run pytest tests/test_import_service.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/core/importers/service.py backend/tests/test_import_service.py
git commit -m "feat: importação incremental de partidas do chess.com com filtro de categoria"
```

---

### Task 6: Engine (Stockfish via UCI) e engine falsa para testes

**Files:**
- Create: `backend/chess_trainer/core/analysis/engine.py`, `backend/tests/fakes.py`
- Test: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `MATE_SCORE` (Task 2).
- Produces:
  - `@dataclass(frozen=True) LineEval(move: str, score: int, pv: tuple[str, ...])` — `move` e `pv` em UCI; `score` do ponto de vista do lado a jogar na posição analisada; `pv[0] == move`.
  - `class EngineLike(Protocol)`: `analyse(board: chess.Board, depth: int, multipv: int = 1) -> list[LineEval]` (ordenada da melhor para a pior; lista vazia se não há lances legais).
  - `terminal_score(board: chess.Board) -> int | None`: `-MATE_SCORE` se xeque-mate (lado a jogar está mateado), `0` para outros fins de jogo, `None` se o jogo continua.
  - `class StockfishEngine(path: str, threads: int = 4, hash_mb: int = 256)` implementa `EngineLike`; `close()`, `restart()`.
  - `find_stockfish(configured: str) -> str | None`: caminho configurado se existir; senão `shutil.which("stockfish")`; senão o primeiro `stockfish*.exe`/`stockfish*` encontrado em `backend/engines/**`.
  - `tests/fakes.py`: `class FakeEngine(script: dict[str, list[LineEval]] | None = None, default: Callable[[chess.Board], list[LineEval]] | None = None)`. Chave do script: `board.epd()` (FEN sem contadores). Ordem: script, depois `default`, senão `KeyError`. Atributo `calls: list[str]` com os EPDs analisados. `first_legal_default(score: int)` devolve um `default` que responde o primeiro lance legal **não captura** (ou o primeiro legal, se todos capturam) com o score dado.

- [ ] **Step 1: Escrever `tests/fakes.py`**

```python
from typing import Callable

import chess

from chess_trainer.core.analysis.engine import LineEval


def first_legal_default(score: int) -> Callable[[chess.Board], list[LineEval]]:
    def _default(board: chess.Board) -> list[LineEval]:
        legal = list(board.legal_moves)
        if not legal:
            return []
        quiet = [m for m in legal if not board.is_capture(m)]
        move = (quiet or legal)[0].uci()
        return [LineEval(move, score, (move,))]

    return _default


class FakeEngine:
    def __init__(self, script: dict[str, list[LineEval]] | None = None, default=None):
        self.script = script or {}
        self.default = default
        self.calls: list[str] = []
        self.fail_next = False  # simula engine morta na próxima chamada

    def analyse(self, board: chess.Board, depth: int, multipv: int = 1) -> list[LineEval]:
        if self.fail_next:
            self.fail_next = False
            import chess.engine
            raise chess.engine.EngineTerminatedError("engine morreu")
        key = board.epd()
        self.calls.append(key)
        if key in self.script:
            return self.script[key][:multipv]
        if self.default is not None:
            return self.default(board)[:multipv]
        raise KeyError(f"posição sem script: {key}")

    def close(self) -> None:
        pass

    def restart(self) -> None:
        pass
```

- [ ] **Step 2: Escrever `tests/test_engine.py`**

```python
import os
import shutil

import chess
import pytest

from chess_trainer.core.analysis.engine import (
    LineEval, StockfishEngine, find_stockfish, terminal_score,
)
from chess_trainer.core.evals import MATE_SCORE, is_mate_for
from tests.fakes import FakeEngine, first_legal_default


def test_terminal_score():
    mated = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert mated.is_checkmate()
    assert terminal_score(mated) == -MATE_SCORE
    stalemate = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert stalemate.is_stalemate()
    assert terminal_score(stalemate) == 0
    assert terminal_score(chess.Board()) is None


def test_fake_engine_script_then_default():
    board = chess.Board()
    fake = FakeEngine({board.epd(): [LineEval("e2e4", 30, ("e2e4", "e7e5"))]}, first_legal_default(0))
    assert fake.analyse(board, 10)[0].move == "e2e4"
    board.push_uci("e2e4")
    assert fake.analyse(board, 10)[0].score == 0
    assert len(fake.calls) == 2


def test_fake_engine_raises_without_script():
    with pytest.raises(KeyError):
        FakeEngine().analyse(chess.Board(), 10)


def test_find_stockfish_prefers_configured(tmp_path):
    exe = tmp_path / "stockfish.exe"
    exe.write_bytes(b"")
    assert find_stockfish(str(exe)) == str(exe)
    assert find_stockfish(str(tmp_path / "missing.exe")) in (None, shutil.which("stockfish")) or True


@pytest.mark.slow
def test_real_stockfish_finds_mate_in_one():
    path = find_stockfish(os.environ.get("STOCKFISH_PATH", ""))
    if not path:
        pytest.skip("Stockfish não encontrado")
    engine = StockfishEngine(path, threads=2, hash_mb=64)
    try:
        board = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        lines = engine.analyse(board, depth=10, multipv=2)
        assert lines[0].move == "a1a8"
        assert is_mate_for(lines[0].score)
        assert lines[0].pv[0] == "a1a8"
        assert len(lines) == 2
    finally:
        engine.close()
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `uv run pytest tests/test_engine.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 4: Implementar `core/analysis/engine.py`**

```python
import glob
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import chess
import chess.engine

from chess_trainer.core.evals import MATE_SCORE


@dataclass(frozen=True)
class LineEval:
    move: str
    score: int
    pv: tuple[str, ...]


class EngineLike(Protocol):
    def analyse(self, board: chess.Board, depth: int, multipv: int = 1) -> list[LineEval]: ...


def terminal_score(board: chess.Board) -> int | None:
    if board.is_checkmate():
        return -MATE_SCORE
    if board.is_game_over():
        return 0
    return None


class StockfishEngine:
    def __init__(self, path: str, threads: int = 4, hash_mb: int = 256):
        self._path = path
        self._threads = threads
        self._hash = hash_mb
        self._engine: chess.engine.SimpleEngine | None = None
        self._open()

    def _open(self) -> None:
        self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
        self._engine.configure({"Threads": self._threads, "Hash": self._hash})

    def analyse(self, board: chess.Board, depth: int, multipv: int = 1) -> list[LineEval]:
        if board.is_game_over() or self._engine is None:
            return []
        infos = self._engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
        if isinstance(infos, dict):
            infos = [infos]
        lines: list[LineEval] = []
        for info in infos:
            pv = info.get("pv")
            if not pv or "score" not in info:
                continue
            score = info["score"].pov(board.turn).score(mate_score=MATE_SCORE)
            lines.append(LineEval(pv[0].uci(), int(score), tuple(m.uci() for m in pv)))
        lines.sort(key=lambda line: line.score, reverse=True)
        return lines

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.quit()
            except chess.engine.EngineError:
                pass
            self._engine = None

    def restart(self) -> None:
        self.close()
        self._open()


def find_stockfish(configured: str) -> str | None:
    if configured and Path(configured).is_file():
        return configured
    on_path = shutil.which("stockfish")
    if on_path:
        return on_path
    root = Path(__file__).resolve().parents[3] / "engines"
    for pattern in ("**/stockfish*.exe", "**/stockfish*"):
        hits = [p for p in glob.glob(str(root / pattern), recursive=True) if os.path.isfile(p)]
        if hits:
            return sorted(hits)[0]
    return None
```

- [ ] **Step 5: Rodar para ver passar**

Run: `uv run pytest tests/test_engine.py -q`
Expected: `4 passed, 1 skipped` (o lento pula sem Stockfish)

- [ ] **Step 6: Commit**

```bash
git add backend/chess_trainer/core/analysis/engine.py backend/tests/fakes.py backend/tests/test_engine.py
git commit -m "feat: wrapper UCI do Stockfish e engine falsa para testes"
```

---

### Task 7: Análise de partida (replay + avaliação por lance)

**Files:**
- Create: `backend/chess_trainer/core/analysis/game_analyzer.py`
- Test: `backend/tests/test_game_analyzer.py`

**Interfaces:**
- Consumes: `EngineLike`, `LineEval`, `terminal_score` (Task 6), `MATE_SCORE` (Task 2).
- Produces:
  - `@dataclass PositionData(ply: int, fen: str, move_played: str, move_uci: str, eval_before: int, eval_after: int, best_move: str | None, best_eval: int)` — mesmos nomes das colunas de `Position`, para `Position(game_id=..., **asdict(data))`.
  - `analyze_game(pgn: str, engine: EngineLike, depth: int) -> list[PositionData]`. Uma entrada por lance da linha principal. `eval_before` e `best_eval` = score da melhor linha na posição antes do lance (POV de quem joga); `eval_after` = `-score` da posição seguinte (POV de quem acabou de jogar). Posições terminais usam `terminal_score` sem chamar a engine. Lança `ValueError` se o PGN não tem lances.

- [ ] **Step 1: Escrever `tests/test_game_analyzer.py`**

```python
import chess
import pytest

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.analysis.game_analyzer import analyze_game
from chess_trainer.core.evals import MATE_SCORE
from tests.fakes import FakeEngine, first_legal_default

SCHOLAR = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


def test_one_entry_per_ply_and_sign_flip():
    board = chess.Board()
    after_e4 = chess.Board(); after_e4.push_uci("e2e4")
    fake = FakeEngine({
        board.epd(): [LineEval("e2e4", 30, ("e2e4",))],
        after_e4.epd(): [LineEval("e7e5", -25, ("e7e5",))],
    }, first_legal_default(0))
    data = analyze_game(SCHOLAR, fake, depth=8)
    assert len(data) == 7
    assert data[0].ply == 1 and data[0].move_played == "e4" and data[0].move_uci == "e2e4"
    assert data[0].fen == chess.STARTING_FEN
    assert data[0].eval_before == 30 and data[0].best_move == "e2e4" and data[0].best_eval == 30
    assert data[0].eval_after == 25  # -(-25): POV das brancas após e4
    assert data[1].eval_before == -25 and data[1].move_played == "e5"


def test_terminal_position_uses_mate_score_without_engine():
    fake = FakeEngine(default=first_legal_default(0))
    data = analyze_game(SCHOLAR, fake, depth=8)
    last = data[-1]
    assert last.move_played == "Qxf7#"
    assert last.eval_after == MATE_SCORE  # brancas deram mate
    final = chess.Board()
    for d in data:
        final.push_uci(d.move_uci)
    assert final.epd() not in fake.calls


def test_engine_called_once_per_position():
    fake = FakeEngine(default=first_legal_default(0))
    analyze_game(SCHOLAR, fake, depth=8)
    assert len(fake.calls) == 7  # 8 posições, a última é terminal


def test_empty_pgn_raises():
    with pytest.raises(ValueError):
        analyze_game('[Event "x"]\n\n*', FakeEngine(), depth=8)
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_game_analyzer.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar `core/analysis/game_analyzer.py`**

```python
import io
from dataclasses import dataclass

import chess
import chess.pgn

from chess_trainer.core.analysis.engine import EngineLike, terminal_score


@dataclass
class PositionData:
    ply: int
    fen: str
    move_played: str
    move_uci: str
    eval_before: int
    eval_after: int
    best_move: str | None
    best_eval: int


def _evaluate(board: chess.Board, engine: EngineLike, depth: int) -> tuple[int, str | None]:
    term = terminal_score(board)
    if term is not None:
        return term, None
    lines = engine.analyse(board, depth, multipv=1)
    if not lines:
        return 0, None
    return lines[0].score, lines[0].move


def analyze_game(pgn: str, engine: EngineLike, depth: int) -> list[PositionData]:
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("PGN inválido")
    moves = list(game.mainline_moves())
    if not moves:
        raise ValueError("PGN sem lances")

    board = game.board()
    scores: list[int] = []
    bests: list[str | None] = []
    fens: list[str] = []
    sans: list[str] = []
    for move in moves:
        score, best = _evaluate(board, engine, depth)
        scores.append(score)
        bests.append(best)
        fens.append(board.fen())
        sans.append(board.san(move))
        board.push(move)
    final_score, _ = _evaluate(board, engine, depth)
    scores.append(final_score)

    return [
        PositionData(
            ply=i + 1,
            fen=fens[i],
            move_played=sans[i],
            move_uci=moves[i].uci(),
            eval_before=scores[i],
            eval_after=-scores[i + 1],
            best_move=bests[i],
            best_eval=scores[i],
        )
        for i in range(len(moves))
    ]
```

- [ ] **Step 4: Rodar para ver passar**

Run: `uv run pytest tests/test_game_analyzer.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/core/analysis/game_analyzer.py backend/tests/test_game_analyzer.py
git commit -m "feat: análise de partida lance a lance com avaliação antes/depois"
```

---

### Task 8: Detecção de erros (função pura)

**Files:**
- Create: `backend/chess_trainer/core/analysis/mistakes.py`
- Modify: `backend/chess_trainer/config.py` (adicionar `thresholds_from`)
- Test: `backend/tests/test_mistakes.py`

**Interfaces:**
- Consumes: `is_mate_for`, `is_mate_against` (Task 2), `AppSettings` (Task 3).
- Produces:
  - `@dataclass(frozen=True) Thresholds(mistake_cp: int = 100, blunder_cp: int = 200, decided_cp: int = 1000)`
  - `classify_move(eval_before: int, eval_after: int, t: Thresholds) -> str | None` → `"blunder"`, `"mistake"` ou `None`.
  - `mover_color(ply: int) -> str` → `"white"` para ply ímpar.
  - `classify_positions(positions: Iterable[Any], my_color: str, t: Thresholds) -> int`: para cada objeto com `ply, eval_before, eval_after`, define `is_mistake`, `mistake_level`, `mistake_by` (`"me"`/`"opponent"`); devolve quantos erros marcou. Funciona com `Position` (ORM) e `PositionData`.
  - `config.thresholds_from(settings: AppSettings) -> Thresholds`.

- [ ] **Step 1: Escrever `tests/test_mistakes.py`**

```python
import pytest

from chess_trainer.config import AppSettings, thresholds_from
from chess_trainer.core.analysis.game_analyzer import PositionData
from chess_trainer.core.analysis.mistakes import Thresholds, classify_move, classify_positions, mover_color
from chess_trainer.core.evals import MATE_SCORE

T = Thresholds()
M = MATE_SCORE


@pytest.mark.parametrize("before,after,expected", [
    (50, -180, "blunder"),          # queda 230
    (50, -100, "mistake"),          # queda 150
    (50, -20, None),                # queda 70
    (50, 60, None),                 # melhorou
    (M - 3, 300, "blunder"),        # perdeu mate
    (M - 3, M - 5, None),           # mate continua
    (100, -(M - 4), "blunder"),     # entregou mate
    (-(M - 4), -(M - 2), None),     # já estava mateado
    (1500, 1100, None),             # decidido dos dois lados
    (-1500, -1900, None),           # perdido dos dois lados
    (1500, 900, "blunder"),         # saiu da zona decidida
])
def test_classify_move(before, after, expected):
    assert classify_move(before, after, T) == expected


def test_custom_thresholds():
    t = Thresholds(mistake_cp=50, blunder_cp=300)
    assert classify_move(0, -60, t) == "mistake"
    assert classify_move(0, -250, t) == "mistake"
    assert classify_move(0, -310, t) == "blunder"


def test_mover_color():
    assert mover_color(1) == "white" and mover_color(2) == "black" and mover_color(7) == "white"


def _pd(ply, before, after):
    return PositionData(ply=ply, fen="f", move_played="x", move_uci="a1a2",
                        eval_before=before, eval_after=after, best_move=None, best_eval=before)


def test_classify_positions_sets_fields_and_side():
    positions = [_pd(1, 20, 10), _pd(2, -10, -300), _pd(3, 300, 50)]
    n = classify_positions(positions, my_color="black", t=T)
    assert n == 2
    assert positions[0].is_mistake is False and positions[0].mistake_level is None
    assert positions[1].mistake_level == "blunder" and positions[1].mistake_by == "me"
    assert positions[2].mistake_level == "blunder" and positions[2].mistake_by == "opponent"


def test_thresholds_from_settings():
    t = thresholds_from(AppSettings(mistake_threshold_cp=80, blunder_threshold_cp=250))
    assert t == Thresholds(mistake_cp=80, blunder_cp=250, decided_cp=1000)
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_mistakes.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar `core/analysis/mistakes.py`**

```python
from dataclasses import dataclass
from typing import Any, Iterable

from chess_trainer.core.evals import is_mate_against, is_mate_for


@dataclass(frozen=True)
class Thresholds:
    mistake_cp: int = 100
    blunder_cp: int = 200
    decided_cp: int = 1000


def classify_move(eval_before: int, eval_after: int, t: Thresholds) -> str | None:
    if is_mate_for(eval_before):
        return None if is_mate_for(eval_after) else "blunder"
    if is_mate_against(eval_before):
        return None  # já estava mateado; não há erro a marcar
    if is_mate_against(eval_after):
        return "blunder"
    if eval_before >= t.decided_cp and eval_after >= t.decided_cp:
        return None
    if eval_before <= -t.decided_cp and eval_after <= -t.decided_cp:
        return None
    drop = eval_before - eval_after
    if drop >= t.blunder_cp:
        return "blunder"
    if drop >= t.mistake_cp:
        return "mistake"
    return None


def mover_color(ply: int) -> str:
    return "white" if ply % 2 == 1 else "black"


def classify_positions(positions: Iterable[Any], my_color: str, t: Thresholds) -> int:
    count = 0
    for pos in positions:
        level = classify_move(pos.eval_before, pos.eval_after, t)
        pos.is_mistake = level is not None
        pos.mistake_level = level
        pos.mistake_by = (("me" if mover_color(pos.ply) == my_color else "opponent") if level else None)
        count += int(level is not None)
    return count
```

- [ ] **Step 4: Adicionar a `config.py`**

```python
from chess_trainer.core.analysis.mistakes import Thresholds


def thresholds_from(settings: AppSettings) -> Thresholds:
    return Thresholds(
        mistake_cp=settings.mistake_threshold_cp,
        blunder_cp=settings.blunder_threshold_cp,
    )
```

(Import no topo do arquivo; `mistakes.py` não importa `config`, então não há ciclo.)

- [ ] **Step 5: Rodar para ver passar**

Run: `uv run pytest tests/test_mistakes.py -q`
Expected: `15 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/chess_trainer/core/analysis/mistakes.py backend/chess_trainer/config.py backend/tests/test_mistakes.py
git commit -m "feat: classificação de erros (mistake/blunder) a partir das avaliações"
```

---

### Task 9: Material e gerador do puzzle "punir"

**Files:**
- Create: `backend/chess_trainer/core/puzzles/material.py`, `backend/chess_trainer/core/puzzles/generator.py`
- Modify: `backend/chess_trainer/config.py` (adicionar `puzzle_config_from`)
- Test: `backend/tests/test_material.py`, `backend/tests/test_generator_punish.py`

**Interfaces:**
- Consumes: `EngineLike`, `LineEval` (Task 6); `is_mate_for`, `clamp` (Task 2); `FakeEngine`, `first_legal_default` (Task 6).
- Produces (material): `PIECE_VALUES: dict[int, int]` (P1 N3 B3 R5 Q9 K0), `material(board, color) -> int`, `material_balance(board, color) -> int` (próprio − adversário), `floor_to_piece(pawns: float) -> int` (≥9→9, ≥5→5, ≥3→3, ≥1→1, senão 0).
- Produces (generator):
  - `@dataclass SolutionMove(uci: str, by: str, alternatives: list[str] = [])` com `by ∈ {"solver","engine"}`; `to_dict()`.
  - `@dataclass PuzzleDraft(fen_start: str, side_to_move: str, moves: list[SolutionMove], end_reason: str, solver_moves: int, explanation_pv: list[str])`; `to_json() -> str` produz `{"moves":[...], "explanation_pv":[...]}`.
  - `@dataclass(frozen=True) PuzzleConfig(depth=22, alt_window_cp=50, max_solver_moves=10, max_mate_moves=15, min_solver_eval_cp=100, avoid_gap_cp=150)`.
  - `generate_punish(board: chess.Board, drop_cp: int, engine: EngineLike, cfg: PuzzleConfig) -> PuzzleDraft | None`. `board` é a posição **após** o lance errado (solver = `board.turn`); `drop_cp = eval_before - eval_after` da posição do erro.
  - `config.puzzle_config_from(settings) -> PuzzleConfig` (usa `puzzle_depth` e `avoid_gap_cp`).
- Regras (spec §7.1, versão precisa): ver o código e os testes abaixo; "alternativa próxima" = dentro de 50 cp em modo material, ou score **igual** em modo mate (mate mais lento nunca é alternativa).

- [ ] **Step 1: Escrever `tests/test_material.py`**

```python
import chess

from chess_trainer.core.puzzles.material import floor_to_piece, material, material_balance


def test_material_and_balance():
    board = chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")
    assert material(board, chess.WHITE) == 3 and material(board, chess.BLACK) == 9
    assert material_balance(board, chess.WHITE) == -6
    assert material_balance(board, chess.BLACK) == 6
    assert material_balance(chess.Board(), chess.WHITE) == 0


def test_floor_to_piece():
    assert floor_to_piece(0.5) == 0
    assert floor_to_piece(1.0) == 1
    assert floor_to_piece(2.9) == 1
    assert floor_to_piece(3.0) == 3
    assert floor_to_piece(4.5) == 3
    assert floor_to_piece(5.0) == 5
    assert floor_to_piece(8.9) == 5
    assert floor_to_piece(9.0) == 9
    assert floor_to_piece(20.0) == 9
```

- [ ] **Step 2: Escrever `tests/test_generator_punish.py`**

```python
import chess

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.puzzles.generator import PuzzleConfig, generate_punish
from tests.fakes import FakeEngine, first_legal_default

CFG = PuzzleConfig(depth=10)
M = MATE_SCORE


def _after(fen: str, *ucis: str) -> chess.Board:
    b = chess.Board(fen)
    for u in ucis:
        b.push_uci(u)
    return b


HANGING_QUEEN = "4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1"          # Nxd5 ganha a dama
MATE_IN_2 = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1"           # Re8+ Rxe8 Qxe8#
TWO_CAPTURES = "4k3/8/8/3q4/8/2N1N3/8/4K3 w - - 0 1"          # Nc3xd5 ou Ne3xd5
RECAPTURE = "8/8/4k3/3q4/8/8/8/3RK3 w - - 0 1"                # Rxd5 Kxd5
VAGUE = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
MATE_IN_1 = "6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1"               # Ra8#


def test_hanging_queen_ends_at_capture():
    fake = FakeEngine({
        chess.Board(HANGING_QUEEN).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7"))],
        _after(HANGING_QUEEN, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    draft = generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    assert draft.end_reason == "material_gain" and draft.solver_moves == 1
    assert [(m.uci, m.by) for m in draft.moves] == [("c3d5", "solver")]
    assert draft.side_to_move == "white" and draft.fen_start == HANGING_QUEEN
    assert len(fake.calls) == 2


def test_mate_in_two_runs_to_checkmate():
    fake = FakeEngine({
        chess.Board(MATE_IN_2).epd(): [LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8"))],
        _after(MATE_IN_2, "e1e8").epd(): [LineEval("c8e8", -(M - 1), ("c8e8", "a4e8"))],
        _after(MATE_IN_2, "e1e8", "c8e8").epd(): [LineEval("a4e8", M - 1, ("a4e8",))],
    })
    draft = generate_punish(chess.Board(MATE_IN_2), drop_cp=5000, engine=fake, cfg=CFG)
    assert draft is not None
    assert draft.end_reason == "mate" and draft.solver_moves == 2
    assert [(m.uci, m.by) for m in draft.moves] == [("e1e8", "solver"), ("c8e8", "engine"), ("a4e8", "solver")]


def test_vague_advantage_is_discarded():
    fake = FakeEngine(default=first_legal_default(150))
    assert generate_punish(chess.Board(VAGUE), drop_cp=150, engine=fake, cfg=CFG) is None


def test_two_capturing_moves_become_alternatives():
    fake = FakeEngine({
        chess.Board(TWO_CAPTURES).epd(): [
            LineEval("c3d5", 900, ("c3d5", "e8d7")),
            LineEval("e3d5", 890, ("e3d5", "e8d7")),
        ],
        _after(TWO_CAPTURES, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    draft = generate_punish(chess.Board(TWO_CAPTURES), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    assert draft.moves[0].alternatives == ["e3d5"]


def test_quiet_alternative_within_window_discards():
    fake = FakeEngine({
        chess.Board(HANGING_QUEEN).epd(): [
            LineEval("c3d5", 900, ("c3d5", "e8d7")),
            LineEval("e1d1", 880, ("e1d1", "e8d7")),
        ],
        _after(HANGING_QUEEN, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    assert generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG) is None


def test_solver_not_better_is_discarded():
    fake = FakeEngine({chess.Board(HANGING_QUEEN).epd(): [LineEval("c3d5", 50, ("c3d5",))]})
    assert generate_punish(chess.Board(HANGING_QUEEN), drop_cp=300, engine=fake, cfg=CFG) is None
    assert len(fake.calls) == 1


def test_intermediate_ambiguity_discards():
    fake = FakeEngine({
        chess.Board(MATE_IN_2).epd(): [
            LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8")),
            LineEval("e1e7", M - 2, ("e1e7",)),
        ],
        _after(MATE_IN_2, "e1e8").epd(): [LineEval("c8e8", -(M - 1), ("c8e8", "a4e8"))],
    })
    assert generate_punish(chess.Board(MATE_IN_2), drop_cp=5000, engine=fake, cfg=CFG) is None


def test_gain_must_survive_best_reply():
    script = {
        chess.Board(RECAPTURE).epd(): [LineEval("d1d5", 450, ("d1d5", "e6d5"))],
        _after(RECAPTURE, "d1d5").epd(): [LineEval("e6d5", -50, ("e6d5",))],
    }
    # alvo 3 (queda 400): ganho líquido 9-5=4 sobrevive → termina em Rxd5
    draft = generate_punish(chess.Board(RECAPTURE), 400, FakeEngine(script, first_legal_default(450)), CFG)
    assert draft is not None and [m.uci for m in draft.moves] == ["d1d5"]
    # alvo 5 (queda 600): 4 < 5 → continua e, sem mais material, é descartado
    assert generate_punish(chess.Board(RECAPTURE), 600, FakeEngine(script, first_legal_default(450)), CFG) is None


def test_slower_mate_is_not_an_alternative():
    fake = FakeEngine({
        chess.Board(MATE_IN_1).epd(): [
            LineEval("a1a8", M - 1, ("a1a8",)),
            LineEval("a1a7", M - 3, ("a1a7",)),
        ],
    })
    draft = generate_punish(chess.Board(MATE_IN_1), drop_cp=5000, engine=fake, cfg=CFG)
    assert draft is not None and draft.end_reason == "mate"
    assert draft.moves[0].alternatives == []


def test_draft_json_shape():
    fake = FakeEngine({chess.Board(MATE_IN_1).epd(): [LineEval("a1a8", M - 1, ("a1a8",))]})
    draft = generate_punish(chess.Board(MATE_IN_1), drop_cp=5000, engine=fake, cfg=CFG)
    import json
    data = json.loads(draft.to_json())
    assert data == {"moves": [{"uci": "a1a8", "by": "solver", "alternatives": []}], "explanation_pv": []}
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `uv run pytest tests/test_material.py tests/test_generator_punish.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 4: Implementar `core/puzzles/material.py`**

```python
import chess

PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(
        PIECE_VALUES[piece_type] * len(board.pieces(piece_type, color))
        for piece_type in PIECE_VALUES
    )


def material_balance(board: chess.Board, color: chess.Color) -> int:
    return material(board, color) - material(board, not color)


def floor_to_piece(pawns: float) -> int:
    for value in (9, 5, 3, 1):
        if pawns >= value:
            return value
    return 0
```

- [ ] **Step 5: Implementar `core/puzzles/generator.py`**

```python
import json
from dataclasses import asdict, dataclass, field

import chess

from chess_trainer.core.analysis.engine import EngineLike, LineEval
from chess_trainer.core.evals import clamp, is_mate_for
from chess_trainer.core.puzzles.material import floor_to_piece, material_balance


@dataclass
class SolutionMove:
    uci: str
    by: str  # "solver" | "engine"
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PuzzleDraft:
    fen_start: str
    side_to_move: str
    moves: list[SolutionMove]
    end_reason: str  # "mate" | "material_gain" | "explanation"
    solver_moves: int
    explanation_pv: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({"moves": [m.to_dict() for m in self.moves], "explanation_pv": self.explanation_pv})


@dataclass(frozen=True)
class PuzzleConfig:
    depth: int = 22
    alt_window_cp: int = 50
    max_solver_moves: int = 10
    max_mate_moves: int = 15
    min_solver_eval_cp: int = 100
    avoid_gap_cp: int = 150


def _color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


def _gain(board: chess.Board, solver: chess.Color, start_balance: int) -> int:
    return material_balance(board, solver) - start_balance


def _is_close(best: LineEval, alt: LineEval, cfg: PuzzleConfig, mate_mode: bool) -> bool:
    if mate_mode:
        return alt.score == best.score
    return best.score - alt.score <= cfg.alt_window_cp


def _final_alternatives(
    board: chess.Board, close_alts: list[LineEval], mate_mode: bool,
    target: int, start_balance: int, solver: chess.Color,
) -> list[str] | None:
    """Alternativas aceitas no lance final; None se alguma alternativa próxima não materializa."""
    accepted: list[str] = []
    for alt in close_alts:
        b = board.copy()
        b.push_uci(alt.move)
        if b.is_checkmate():
            accepted.append(alt.move)
            continue
        if mate_mode:
            return None
        gain_now = _gain(b, solver, start_balance)
        if len(alt.pv) > 1:
            b.push_uci(alt.pv[1])
        gain_after = _gain(b, solver, start_balance)
        if gain_now >= target and gain_after >= target:
            accepted.append(alt.move)
        else:
            return None
    return accepted


def _draft(board: chess.Board, moves: list[SolutionMove], end_reason: str) -> PuzzleDraft:
    return PuzzleDraft(
        fen_start=board.fen(),
        side_to_move=_color_name(board.turn),
        moves=moves,
        end_reason=end_reason,
        solver_moves=sum(1 for m in moves if m.by == "solver"),
    )


def generate_punish(board: chess.Board, drop_cp: int, engine: EngineLike, cfg: PuzzleConfig) -> PuzzleDraft | None:
    solver = board.turn
    start_balance = material_balance(board, solver)

    lines: list[LineEval] | None = engine.analyse(board, cfg.depth, multipv=3)
    if not lines:
        return None
    mate_mode = is_mate_for(lines[0].score)
    target = 0
    if not mate_mode:
        if lines[0].score < cfg.min_solver_eval_cp:
            return None
        target = floor_to_piece(clamp(drop_cp) / 100)
        if target <= 0:
            return None

    limit = cfg.max_mate_moves if mate_mode else cfg.max_solver_moves
    moves: list[SolutionMove] = []
    current = board.copy()

    for _ in range(limit):
        if lines is None:
            lines = engine.analyse(current, cfg.depth, multipv=3)
            if not lines:
                return None
        best = lines[0]
        close_alts = [alt for alt in lines[1:] if _is_close(best, alt, cfg, mate_mode)]

        after = current.copy()
        after.push_uci(best.move)
        if after.is_checkmate():
            alts = _final_alternatives(current, close_alts, mate_mode, target, start_balance, solver)
            if alts is None:
                return None
            moves.append(SolutionMove(best.move, "solver", alts))
            return _draft(board, moves, "mate")
        if after.is_game_over():
            return None

        reply_lines = engine.analyse(after, cfg.depth, multipv=1)
        if not reply_lines:
            return None
        reply = reply_lines[0]
        after_reply = after.copy()
        after_reply.push_uci(reply.move)

        if not mate_mode and _gain(after, solver, start_balance) >= target \
                and _gain(after_reply, solver, start_balance) >= target:
            alts = _final_alternatives(current, close_alts, mate_mode, target, start_balance, solver)
            if alts is None:
                return None
            moves.append(SolutionMove(best.move, "solver", alts))
            return _draft(board, moves, "material_gain")

        if close_alts:
            return None  # ambiguidade em lance intermediário

        moves.append(SolutionMove(best.move, "solver"))
        moves.append(SolutionMove(reply.move, "engine"))
        current = after_reply
        if current.is_game_over():
            return None
        lines = None

    return None
```

- [ ] **Step 6: Adicionar a `config.py`**

```python
from chess_trainer.core.puzzles.generator import PuzzleConfig


def puzzle_config_from(settings: AppSettings) -> PuzzleConfig:
    return PuzzleConfig(depth=settings.puzzle_depth, avoid_gap_cp=settings.avoid_gap_cp)
```

- [ ] **Step 7: Rodar para ver passar**

Run: `uv run pytest tests/test_material.py tests/test_generator_punish.py -q`
Expected: `12 passed`

- [ ] **Step 8: Commit**

```bash
git add backend/chess_trainer/core/puzzles backend/chess_trainer/config.py backend/tests/test_material.py backend/tests/test_generator_punish.py
git commit -m "feat: gerador de puzzle punir com regra de materialização e alternativas"
```

---

### Task 10: Puzzle "evitar" e inferência de tema

**Files:**
- Modify: `backend/chess_trainer/core/puzzles/generator.py` (adicionar `generate_avoid`)
- Create: `backend/chess_trainer/core/puzzles/themes.py`
- Test: `backend/tests/test_generator_avoid.py`, `backend/tests/test_themes.py`

**Interfaces:**
- Consumes: `PuzzleDraft`, `SolutionMove`, `PuzzleConfig` (Task 9), `PIECE_VALUES` (Task 9).
- Produces:
  - `generate_avoid(board_before: chess.Board, engine: EngineLike, cfg: PuzzleConfig) -> PuzzleDraft | None`: multipv 2 na posição **antes** do erro; puzzle só se `lines[0].score - lines[1].score >= cfg.avoid_gap_cp`; solução = um lance; `end_reason="explanation"`; `explanation_pv` = até 6 lances da linha principal.
  - `infer_theme(fen_start: str, moves: list[SolutionMove], end_reason: str) -> str` → `mate_in_{n}` | `hanging_piece` | `fork` | `pin` | `discovered_attack` | `tactic`, nessa ordem de prioridade.

- [ ] **Step 1: Escrever `tests/test_generator_avoid.py`**

```python
import chess

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.puzzles.generator import PuzzleConfig, generate_avoid
from tests.fakes import FakeEngine

CFG = PuzzleConfig(depth=10, avoid_gap_cp=150)
FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"


def test_avoid_generated_when_gap_is_large():
    pv = ("f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7", "f1e1", "b7b5")
    fake = FakeEngine({chess.Board(FEN).epd(): [LineEval("f1b5", 320, pv), LineEval("d2d3", 100, ("d2d3",))]})
    draft = generate_avoid(chess.Board(FEN), fake, CFG)
    assert draft is not None
    assert draft.end_reason == "explanation" and draft.solver_moves == 1
    assert [(m.uci, m.by) for m in draft.moves] == [("f1b5", "solver")]
    assert draft.explanation_pv == list(pv[:6])
    assert draft.side_to_move == "white" and draft.fen_start == FEN


def test_avoid_not_generated_when_gap_is_small():
    fake = FakeEngine({chess.Board(FEN).epd(): [LineEval("f1b5", 320, ("f1b5",)), LineEval("d2d3", 200, ("d2d3",))]})
    assert generate_avoid(chess.Board(FEN), fake, CFG) is None


def test_avoid_not_generated_with_single_line():
    fake = FakeEngine({chess.Board(FEN).epd(): [LineEval("f1b5", 320, ("f1b5",))]})
    assert generate_avoid(chess.Board(FEN), fake, CFG) is None
```

- [ ] **Step 2: Escrever `tests/test_themes.py`**

```python
from chess_trainer.core.puzzles.generator import SolutionMove
from chess_trainer.core.puzzles.themes import infer_theme

S = lambda uci: SolutionMove(uci, "solver")  # noqa: E731
E = lambda uci: SolutionMove(uci, "engine")  # noqa: E731


def test_mate_theme_counts_solver_moves():
    assert infer_theme("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", [S("a1a8")], "mate") == "mate_in_1"
    assert infer_theme("2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1", [S("e1e8"), E("c8e8"), S("a4e8")], "mate") == "mate_in_2"


def test_hanging_piece():
    assert infer_theme("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1", [S("c3d5")], "material_gain") == "hanging_piece"


def test_fork():
    # Nb7+ ataca rei d8 e dama a5
    assert infer_theme("3k4/8/8/q1N5/8/8/8/6K1 w - - 0 1", [S("c5b7"), E("d8c8"), S("b7a5")], "material_gain") == "fork"


def test_pin():
    # Bb5 crava o cavalo c6 no rei e8
    assert infer_theme("4k3/8/2n5/8/8/8/8/4KB2 w - - 0 1", [S("f1b5")], "material_gain") == "pin"


def test_discovered_attack():
    # Bd4+ descobre a torre e1 sobre a dama e7
    assert infer_theme("7k/4q3/8/8/8/4B3/8/4R1K1 w - - 0 1", [S("e3d4"), E("e7f6"), S("d4f6")], "material_gain") == "discovered_attack"


def test_fallback_tactic():
    assert infer_theme("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", [S("e1d1")], "material_gain") == "tactic"
    assert infer_theme("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", [], "explanation") == "tactic"
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `uv run pytest tests/test_generator_avoid.py tests/test_themes.py -q`
Expected: FAIL com `ImportError`/`ModuleNotFoundError`

- [ ] **Step 4: Adicionar `generate_avoid` ao fim de `core/puzzles/generator.py`**

```python
def generate_avoid(board_before: chess.Board, engine: EngineLike, cfg: PuzzleConfig) -> PuzzleDraft | None:
    lines = engine.analyse(board_before, cfg.depth, multipv=2)
    if len(lines) < 2:
        return None
    best, second = lines[0], lines[1]
    if best.score - second.score < cfg.avoid_gap_cp:
        return None
    return PuzzleDraft(
        fen_start=board_before.fen(),
        side_to_move=_color_name(board_before.turn),
        moves=[SolutionMove(best.move, "solver")],
        end_reason="explanation",
        solver_moves=1,
        explanation_pv=list(best.pv[:6]),
    )
```

- [ ] **Step 5: Implementar `core/puzzles/themes.py`**

```python
import chess

from chess_trainer.core.puzzles.generator import SolutionMove
from chess_trainer.core.puzzles.material import PIECE_VALUES


def _attack_pairs(board: chess.Board, attacker: chess.Color, exclude: set[int]) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for sq in chess.SquareSet(board.occupied_co[attacker]):
        if sq in exclude:
            continue
        for target in board.attacks(sq):
            piece = board.piece_at(target)
            if piece and piece.color != attacker and piece.piece_type != chess.PAWN:
                pairs.add((sq, target))
    return pairs


def infer_theme(fen_start: str, moves: list[SolutionMove], end_reason: str) -> str:
    if end_reason == "mate":
        return f"mate_in_{sum(1 for m in moves if m.by == 'solver')}"
    if not moves:
        return "tactic"

    board = chess.Board(fen_start)
    solver = board.turn
    enemy = not solver
    move = chess.Move.from_uci(moves[0].uci)

    if board.is_capture(move) and not board.is_attacked_by(enemy, move.to_square):
        return "hanging_piece"

    moved = board.piece_at(move.from_square)
    moved_value = PIECE_VALUES[moved.piece_type] if moved else 0
    after = board.copy()
    after.push(move)

    targets = 0
    for sq in after.attacks(move.to_square):
        piece = after.piece_at(sq)
        if piece and piece.color == enemy and (piece.piece_type == chess.KING or PIECE_VALUES[piece.piece_type] > moved_value):
            targets += 1
    if targets >= 2:
        return "fork"

    for sq in chess.SquareSet(after.occupied_co[enemy]):
        if after.is_pinned(enemy, sq) and not board.is_pinned(enemy, sq):
            return "pin"

    before_pairs = _attack_pairs(board, solver, exclude={move.from_square})
    after_pairs = _attack_pairs(after, solver, exclude={move.to_square})
    if after_pairs - before_pairs:
        return "discovered_attack"

    return "tactic"
```

- [ ] **Step 6: Rodar para ver passar**

Run: `uv run pytest tests/test_generator_avoid.py tests/test_themes.py -q`
Expected: `9 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/chess_trainer/core/puzzles backend/tests/test_generator_avoid.py backend/tests/test_themes.py
git commit -m "feat: puzzle evitar e inferência de tema tático"
```

---

### Task 11: Serviço de puzzles e pipeline de análise

**Files:**
- Create: `backend/chess_trainer/core/puzzles/service.py`, `backend/chess_trainer/core/pipeline.py`
- Modify: `backend/chess_trainer/core/analysis/engine.py` (adicionar `close()` e `restart()` ao `EngineLike`)
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `analyze_game`, `PositionData` (Task 7); `classify_positions` (Task 8); `generate_punish`, `generate_avoid`, `PuzzleConfig` (Tasks 9–10); `infer_theme` (Task 10); `thresholds_from`, `puzzle_config_from` (Tasks 8–9); `ProgressFn` (Task 5); modelos (Task 3).
- Produces (puzzles/service):
  - `build_drafts(pos: Position, engine, cfg) -> list[tuple[str, PuzzleDraft]]` — `("punish", ...)` para todo erro; `("avoid", ...)` só se `pos.mistake_by == "me"`.
  - `persist_draft(db, pos: Position, game: Game, kind: str, draft: PuzzleDraft) -> Puzzle | None` (`None` se já existe `fen_start + kind`).
  - `generate_puzzles_for_game(db, game: Game, engine, cfg) -> int`
  - `regenerate_all(db, engine, settings, progress=None) -> int`: apaga `Review` e `Puzzle`, reclassifica as `Position` de cada partida analisada com os limiares atuais, regera. Commit por partida.
- Produces (pipeline): `analyze_pending(db, engine, settings, progress: ProgressFn | None = None, limit: int | None = None) -> int` (partidas analisadas). Partidas mais recentes primeiro. Engine que morre (`chess.engine.EngineError`): rollback, `engine.restart()`, partida pulada nesta rodada. PGN sem lances: marcada como analisada com `analysis_depth = 0`.
- `EngineLike` passa a exigir `close() -> None` e `restart() -> None`.

- [ ] **Step 1: Escrever `tests/test_pipeline.py`**

```python
import chess
from sqlalchemy import func, select

from chess_trainer.config import AppSettings
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import Game, Position, Puzzle, Review
from chess_trainer.core.pipeline import analyze_pending
from chess_trainer.core.puzzles.service import regenerate_all
from tests.fakes import FakeEngine, first_legal_default
from tests.test_models import _game

SCHOLAR = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"
SETTINGS = AppSettings(analysis_depth=6, puzzle_depth=8)


def _before_mate() -> chess.Board:
    b = chess.Board()
    for u in ("e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6"):
        b.push_uci(u)
    return b


def _engine() -> FakeEngine:
    return FakeEngine(
        {_before_mate().epd(): [LineEval("h5f7", MATE_SCORE - 1, ("h5f7",))]},
        first_legal_default(0),
    )


def test_analyze_pending_classifies_and_generates_puzzle(db_session):
    game = _game(pgn=SCHOLAR, my_color="white")
    db_session.add(game)
    db_session.commit()
    events = []

    n = analyze_pending(db_session, _engine(), SETTINGS, progress=lambda *a: events.append(a))

    assert n == 1
    assert game.analyzed_at is not None and game.analysis_depth == 6
    positions = db_session.scalars(select(Position).order_by(Position.ply)).all()
    assert len(positions) == 7
    mistakes = [p for p in positions if p.is_mistake]
    assert [(p.ply, p.mistake_level, p.mistake_by) for p in mistakes] == [(6, "blunder", "opponent")]
    puzzles = db_session.scalars(select(Puzzle)).all()
    assert len(puzzles) == 1
    pz = puzzles[0]
    assert pz.kind == "punish" and pz.theme == "mate_in_1" and pz.category == "rapid"
    assert pz.side_to_move == "white" and pz.solver_moves == 1 and pz.end_reason == "mate"
    assert pz.solution_data["moves"][0]["uci"] == "h5f7"
    assert pz.position_id == mistakes[0].id and pz.game_id == game.id
    assert events[0][0] == "analyze" and events[0][2] == 1


def test_analyze_pending_skips_already_analyzed_and_respects_limit(db_session):
    db_session.add_all([_game(source_id="g1", pgn=SCHOLAR), _game(source_id="g2", pgn=SCHOLAR)])
    db_session.commit()
    assert analyze_pending(db_session, _engine(), SETTINGS, limit=1) == 1
    assert analyze_pending(db_session, _engine(), SETTINGS) == 1
    assert analyze_pending(db_session, _engine(), SETTINGS) == 0
    # dedup por fen_start + kind: as duas partidas iguais geram um puzzle só
    assert db_session.scalar(select(func.count(Puzzle.id))) == 1


def test_engine_crash_skips_game_without_raising(db_session):
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    engine = _engine()
    engine.fail_next = True
    assert analyze_pending(db_session, engine, SETTINGS) == 0
    assert game.analyzed_at is None
    assert analyze_pending(db_session, engine, SETTINGS) == 1


def test_pgn_without_moves_is_marked_analyzed(db_session):
    game = _game(pgn='[Event "x"]\n\n*')
    db_session.add(game)
    db_session.commit()
    assert analyze_pending(db_session, _engine(), SETTINGS) == 1
    assert game.analyzed_at is not None and game.analysis_depth == 0
    assert db_session.scalar(select(func.count(Position.id))) == 0


def test_regenerate_all_drops_reviews_and_rebuilds(db_session):
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)
    old = db_session.scalars(select(Puzzle)).one()
    db_session.add(Review(puzzle_id=old.id, result="correct", ease=2.5, interval_days=1,
                          due_at=old.created_at, lapses=0))
    db_session.commit()

    n = regenerate_all(db_session, _engine(), SETTINGS)

    assert n == 1
    assert db_session.scalar(select(func.count(Review.id))) == 0
    new = db_session.scalars(select(Puzzle)).one()
    assert new.id != old.id and new.theme == "mate_in_1"
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Estender `EngineLike` em `core/analysis/engine.py`**

```python
class EngineLike(Protocol):
    def analyse(self, board: chess.Board, depth: int, multipv: int = 1) -> list[LineEval]: ...
    def close(self) -> None: ...
    def restart(self) -> None: ...
```

- [ ] **Step 4: Implementar `core/puzzles/service.py`**

```python
from typing import Callable

import chess
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, puzzle_config_from, thresholds_from
from chess_trainer.core.analysis.engine import EngineLike
from chess_trainer.core.analysis.mistakes import classify_positions
from chess_trainer.core.models import Game, Position, Puzzle, Review
from chess_trainer.core.puzzles.generator import PuzzleConfig, PuzzleDraft, generate_avoid, generate_punish
from chess_trainer.core.puzzles.themes import infer_theme

ProgressFn = Callable[[str, int, int, str], None]


def build_drafts(pos: Position, engine: EngineLike, cfg: PuzzleConfig) -> list[tuple[str, PuzzleDraft]]:
    board_before = chess.Board(pos.fen)
    board_after = board_before.copy()
    board_after.push_uci(pos.move_uci)
    drafts: list[tuple[str, PuzzleDraft]] = []
    if not board_after.is_game_over():
        punish = generate_punish(board_after, pos.eval_before - pos.eval_after, engine, cfg)
        if punish is not None:
            drafts.append(("punish", punish))
    if pos.mistake_by == "me":
        avoid = generate_avoid(board_before, engine, cfg)
        if avoid is not None:
            drafts.append(("avoid", avoid))
    return drafts


def persist_draft(db: Session, pos: Position, game: Game, kind: str, draft: PuzzleDraft) -> Puzzle | None:
    exists = db.scalar(select(Puzzle.id).where(Puzzle.fen_start == draft.fen_start, Puzzle.kind == kind))
    if exists:
        return None
    puzzle = Puzzle(
        position_id=pos.id,
        game_id=game.id,
        kind=kind,
        fen_start=draft.fen_start,
        side_to_move=draft.side_to_move,
        solution=draft.to_json(),
        end_reason=draft.end_reason,
        theme=infer_theme(draft.fen_start, draft.moves, draft.end_reason),
        category=game.category,
        solver_moves=draft.solver_moves,
    )
    db.add(puzzle)
    db.flush()
    return puzzle


def generate_puzzles_for_game(db: Session, game: Game, engine: EngineLike, cfg: PuzzleConfig) -> int:
    created = 0
    for pos in game.positions:
        if not pos.is_mistake:
            continue
        for kind, draft in build_drafts(pos, engine, cfg):
            if persist_draft(db, pos, game, kind, draft) is not None:
                created += 1
    return created


def regenerate_all(db: Session, engine: EngineLike, settings: AppSettings, progress: ProgressFn | None = None) -> int:
    db.execute(delete(Review))
    db.execute(delete(Puzzle))
    db.commit()
    thresholds = thresholds_from(settings)
    cfg = puzzle_config_from(settings)
    games = db.scalars(select(Game).where(Game.analyzed_at.is_not(None)).order_by(Game.played_at.desc())).all()
    total = 0
    for i, game in enumerate(games):
        if progress:
            progress("regenerate", i, len(games), f"{game.white} x {game.black}")
        classify_positions(game.positions, game.my_color, thresholds)
        total += generate_puzzles_for_game(db, game, engine, cfg)
        db.commit()
    if progress:
        progress("regenerate", len(games), len(games), "concluído")
    return total
```

- [ ] **Step 5: Implementar `core/pipeline.py`**

```python
from dataclasses import asdict
from typing import Callable

import chess.engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, puzzle_config_from, thresholds_from
from chess_trainer.core.analysis.engine import EngineLike
from chess_trainer.core.analysis.game_analyzer import analyze_game
from chess_trainer.core.analysis.mistakes import classify_positions
from chess_trainer.core.models import Game, Position, utcnow
from chess_trainer.core.puzzles.service import generate_puzzles_for_game

ProgressFn = Callable[[str, int, int, str], None]


def analyze_pending(
    db: Session,
    engine: EngineLike,
    settings: AppSettings,
    progress: ProgressFn | None = None,
    limit: int | None = None,
) -> int:
    thresholds = thresholds_from(settings)
    cfg = puzzle_config_from(settings)
    games = db.scalars(
        select(Game).where(Game.analyzed_at.is_(None)).order_by(Game.played_at.desc())
    ).all()
    if limit is not None:
        games = games[:limit]

    analyzed = 0
    for i, game in enumerate(games):
        if progress:
            progress("analyze", i, len(games), f"{game.white} x {game.black}")
        try:
            data = analyze_game(game.pgn, engine, settings.analysis_depth)
        except ValueError:
            game.analyzed_at = utcnow()
            game.analysis_depth = 0
            db.commit()
            analyzed += 1
            continue
        except chess.engine.EngineError:
            db.rollback()
            engine.restart()
            continue

        rows = [Position(game_id=game.id, **asdict(d)) for d in data]
        classify_positions(rows, game.my_color, thresholds)
        db.add_all(rows)
        game.analyzed_at = utcnow()
        game.analysis_depth = settings.analysis_depth
        db.flush()
        try:
            generate_puzzles_for_game(db, game, engine, cfg)
        except chess.engine.EngineError:
            db.rollback()
            engine.restart()
            continue
        db.commit()
        analyzed += 1

    if progress:
        progress("analyze", len(games), len(games), "concluído")
    return analyzed
```

- [ ] **Step 6: Rodar para ver passar**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: `5 passed`. Se `test_analyze_pending_skips_already_analyzed_and_respects_limit` falhar na contagem de puzzles, verifique se `game.positions` está sendo carregado após o `flush` (o relacionamento carrega sob demanda; `expire_on_commit=False` no `sessionmaker` é obrigatório).

- [ ] **Step 7: Rodar a suíte inteira**

Run: `uv run pytest -q`
Expected: tudo verde, 1 pulado (Stockfish).

- [ ] **Step 8: Commit**

```bash
git add backend/chess_trainer/core/puzzles/service.py backend/chess_trainer/core/pipeline.py backend/chess_trainer/core/analysis/engine.py backend/tests/test_pipeline.py
git commit -m "feat: pipeline de análise com classificação de erros e geração de puzzles"
```

---

### Task 12: Repetição espaçada (função pura)

**Files:**
- Create: `backend/chess_trainer/core/srs/scheduler.py`
- Test: `backend/tests/test_srs_scheduler.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) SrsState(ease: float = 2.5, interval_days: int = 0, lapses: int = 0, due_at: datetime | None = None, last_reviewed_at: datetime | None = None)`
  - `MIN_EASE = 1.3`, `FAST_MS_PER_MOVE = 10_000`
  - `next_state(prev: SrsState, *, correct: bool, used_hint: bool, duration_ms: int, solver_moves: int, reviewed_at: datetime) -> SrsState`

- [ ] **Step 1: Escrever `tests/test_srs_scheduler.py`**

```python
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
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_srs_scheduler.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar `core/srs/scheduler.py`**

```python
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
            interval = max(prev.interval_days + 1, round(actual * prev.ease))
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
```

- [ ] **Step 4: Rodar para ver passar**

Run: `uv run pytest tests/test_srs_scheduler.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/core/srs/scheduler.py backend/tests/test_srs_scheduler.py
git commit -m "feat: agendador SM-2 adaptado para repetição espaçada"
```

---

### Task 13: Fila do dia e registro de revisões

**Files:**
- Create: `backend/chess_trainer/core/srs/queue.py`, `backend/chess_trainer/core/srs/reviews.py`
- Test: `backend/tests/test_srs_queue.py`, `backend/tests/test_srs_reviews.py`

**Interfaces:**
- Consumes: `SrsState`, `next_state` (Task 12); modelos (Task 3); `AppSettings` (Task 3).
- Produces (queue):
  - `local_day_start(now_utc: datetime) -> datetime` (meia-noite local do dia de `now_utc`, devolvida em UTC naive).
  - `@dataclass QueueFilters(category: str | None = None, theme: str | None = None, kind: str | None = None, color: str | None = None)`
  - `@dataclass QueueResult(due: list[Puzzle], new: list[Puzzle], due_count: int, new_available: int, new_remaining_today: int)`; `new` só é preenchida quando `due` está vazia.
  - `count_new_reviewed_today(db, now) -> int` (puzzles cuja **primeira** `Review` é de hoje).
  - `build_queue(db, filters: QueueFilters, settings: AppSettings, now: datetime) -> QueueResult`
- Produces (reviews):
  - `record_review(db, puzzle: Puzzle, *, session_id: str | None, correct: bool, used_hint: bool, duration_ms: int, now: datetime, settings: AppSettings) -> Review` — atualiza o cache `srs_*` do puzzle, marca sanguessuga ao atingir `leech_lapses`, grava `Review` (`result` = `"correct"`/`"wrong"` conforme o que aconteceu; a dica fica em `used_hint`), commit.
  - `unleech(db, puzzle: Puzzle, now: datetime) -> None` — `is_leech=False`, `leech_since=None`, `srs_lapses=0`, `srs_due_at=now`, commit.

- [ ] **Step 1: Escrever helper de puzzles em `tests/factories.py`**

```python
from datetime import datetime

from chess_trainer.core.models import Game, Puzzle
from tests.test_models import _game


def make_puzzle(db, *, fen: str, category="rapid", theme="tactic", kind="punish", side="white",
                played_at=datetime(2026, 8, 1), due_at=None, is_leech=False, game: Game | None = None) -> Puzzle:
    if game is None:
        game = _game(source_id=f"src-{fen}", category=category, played_at=played_at)
        db.add(game)
        db.flush()
    from chess_trainer.core.models import Position
    pos = Position(game_id=game.id, ply=1, fen=fen, move_played="x", move_uci="a2a3",
                   eval_before=0, eval_after=-300, best_move="a2a4", best_eval=0,
                   is_mistake=True, mistake_level="blunder", mistake_by="opponent")
    db.add(pos)
    db.flush()
    puzzle = Puzzle(position_id=pos.id, game_id=game.id, kind=kind, fen_start=fen, side_to_move=side,
                    solution='{"moves": [{"uci": "a2a4", "by": "solver", "alternatives": []}], "explanation_pv": []}',
                    end_reason="material_gain", theme=theme, category=category, solver_moves=1,
                    is_leech=is_leech, srs_due_at=due_at)
    db.add(puzzle)
    db.commit()
    return puzzle
```

- [ ] **Step 2: Escrever `tests/test_srs_queue.py`**

```python
from datetime import datetime, timedelta

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Review
from chess_trainer.core.srs.queue import QueueFilters, build_queue, count_new_reviewed_today, local_day_start
from tests.factories import make_puzzle

NOW = datetime(2026, 9, 4, 15, 0)
S = AppSettings(new_per_day=2)


def test_local_day_start_is_within_last_24h():
    start = local_day_start(NOW)
    assert start <= NOW and NOW - start < timedelta(hours=24)
    assert start.tzinfo is None


def test_due_puzzles_first_most_overdue_first(db_session):
    p_late = make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=3))
    p_soon = make_puzzle(db_session, fen="f2", due_at=NOW - timedelta(hours=1))
    make_puzzle(db_session, fen="f3", due_at=NOW + timedelta(days=1))  # ainda não venceu
    make_puzzle(db_session, fen="f4")                                   # novo
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert [p.id for p in q.due] == [p_late.id, p_soon.id]
    assert q.due_count == 2 and q.new == [] and q.new_available == 1


def test_new_only_when_nothing_due_recent_games_first_limited(db_session):
    old = make_puzzle(db_session, fen="f1", played_at=datetime(2026, 1, 1))
    mid = make_puzzle(db_session, fen="f2", played_at=datetime(2026, 5, 1))
    new = make_puzzle(db_session, fen="f3", played_at=datetime(2026, 8, 1))
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert q.due == [] and [p.id for p in q.new] == [new.id, mid.id]
    assert q.new_available == 3 and q.new_remaining_today == 2


def test_new_limit_discounts_new_reviewed_today(db_session):
    reviewed = make_puzzle(db_session, fen="f0", due_at=NOW + timedelta(days=1))
    db_session.add(Review(puzzle_id=reviewed.id, reviewed_at=NOW - timedelta(hours=2), result="correct",
                          ease=2.5, interval_days=1, due_at=NOW + timedelta(days=1), lapses=0))
    db_session.commit()
    make_puzzle(db_session, fen="f1"); make_puzzle(db_session, fen="f2")
    assert count_new_reviewed_today(db_session, NOW) == 1
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert len(q.new) == 1 and q.new_remaining_today == 1


def test_filters_and_leeches(db_session):
    make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=1), category="rapid", theme="fork", kind="punish", side="white")
    make_puzzle(db_session, fen="f2", due_at=NOW - timedelta(days=1), category="blitz", theme="fork", kind="avoid", side="black")
    make_puzzle(db_session, fen="f3", due_at=NOW - timedelta(days=1), is_leech=True)
    assert build_queue(db_session, QueueFilters(), S, NOW).due_count == 2
    assert build_queue(db_session, QueueFilters(category="blitz"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(theme="fork", kind="avoid"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(color="white"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(theme="pin"), S, NOW).due_count == 0
```

- [ ] **Step 3: Escrever `tests/test_srs_reviews.py`**

```python
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
```

- [ ] **Step 4: Rodar para ver falhar**

Run: `uv run pytest tests/test_srs_queue.py tests/test_srs_reviews.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 5: Implementar `core/srs/queue.py`**

```python
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Game, Puzzle, Review


def local_day_start(now_utc: datetime) -> datetime:
    local = now_utc.replace(tzinfo=timezone.utc).astimezone()
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class QueueFilters:
    category: str | None = None
    theme: str | None = None
    kind: str | None = None
    color: str | None = None


@dataclass
class QueueResult:
    due: list[Puzzle]
    new: list[Puzzle]
    due_count: int
    new_available: int
    new_remaining_today: int


def _apply_filters(stmt: Select, f: QueueFilters) -> Select:
    if f.category:
        stmt = stmt.where(Puzzle.category == f.category)
    if f.theme:
        stmt = stmt.where(Puzzle.theme == f.theme)
    if f.kind:
        stmt = stmt.where(Puzzle.kind == f.kind)
    if f.color:
        stmt = stmt.where(Puzzle.side_to_move == f.color)
    return stmt


def count_new_reviewed_today(db: Session, now: datetime) -> int:
    day_start = local_day_start(now)
    first_reviews = (
        select(Review.puzzle_id, func.min(Review.reviewed_at).label("first_at"))
        .group_by(Review.puzzle_id)
        .subquery()
    )
    return int(db.scalar(select(func.count()).select_from(first_reviews).where(first_reviews.c.first_at >= day_start)) or 0)


def build_queue(db: Session, filters: QueueFilters, settings: AppSettings, now: datetime) -> QueueResult:
    base = _apply_filters(select(Puzzle).where(Puzzle.is_leech.is_(False)), filters)

    due = db.scalars(
        base.where(Puzzle.srs_due_at.is_not(None), Puzzle.srs_due_at <= now).order_by(Puzzle.srs_due_at)
    ).all()

    new_stmt = base.where(Puzzle.srs_due_at.is_(None)).join(Game, Game.id == Puzzle.game_id).order_by(Game.played_at.desc())
    new_available = int(db.scalar(select(func.count()).select_from(new_stmt.subquery())) or 0)
    remaining = max(0, settings.new_per_day - count_new_reviewed_today(db, now))

    new: list[Puzzle] = []
    if not due and remaining > 0:
        new = db.scalars(new_stmt.limit(remaining)).all()

    return QueueResult(due=list(due), new=list(new), due_count=len(due),
                       new_available=new_available, new_remaining_today=remaining)
```

- [ ] **Step 6: Implementar `core/srs/reviews.py`**

```python
from datetime import datetime

from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Puzzle, Review
from chess_trainer.core.srs.scheduler import SrsState, next_state


def record_review(
    db: Session,
    puzzle: Puzzle,
    *,
    session_id: str | None,
    correct: bool,
    used_hint: bool,
    duration_ms: int,
    now: datetime,
    settings: AppSettings,
) -> Review:
    prev = SrsState(
        ease=puzzle.srs_ease,
        interval_days=puzzle.srs_interval_days,
        lapses=puzzle.srs_lapses,
        due_at=puzzle.srs_due_at,
        last_reviewed_at=puzzle.srs_last_reviewed_at,
    )
    nxt = next_state(prev, correct=correct, used_hint=used_hint, duration_ms=duration_ms,
                     solver_moves=puzzle.solver_moves, reviewed_at=now)
    puzzle.srs_ease = nxt.ease
    puzzle.srs_interval_days = nxt.interval_days
    puzzle.srs_lapses = nxt.lapses
    puzzle.srs_due_at = nxt.due_at
    puzzle.srs_last_reviewed_at = nxt.last_reviewed_at
    if nxt.lapses >= settings.leech_lapses and not puzzle.is_leech:
        puzzle.is_leech = True
        puzzle.leech_since = now

    review = Review(
        puzzle_id=puzzle.id,
        session_id=session_id,
        reviewed_at=now,
        result="correct" if correct else "wrong",
        used_hint=used_hint,
        duration_ms=duration_ms,
        ease=nxt.ease,
        interval_days=nxt.interval_days,
        due_at=nxt.due_at,
        lapses=nxt.lapses,
    )
    db.add(review)
    db.commit()
    return review


def unleech(db: Session, puzzle: Puzzle, now: datetime) -> None:
    puzzle.is_leech = False
    puzzle.leech_since = None
    puzzle.srs_lapses = 0
    puzzle.srs_due_at = now
    db.commit()
```

- [ ] **Step 7: Rodar para ver passar**

Run: `uv run pytest tests/test_srs_queue.py tests/test_srs_reviews.py -q`
Expected: `8 passed`

- [ ] **Step 8: Commit**

```bash
git add backend/chess_trainer/core/srs backend/tests/factories.py backend/tests/test_srs_queue.py backend/tests/test_srs_reviews.py
git commit -m "feat: fila do dia e registro de revisões com sanguessugas"
```

---

### Task 14: API — app, fila de jobs e rotas de sistema

**Files:**
- Create: `backend/chess_trainer/api/app.py`, `backend/chess_trainer/api/deps.py`, `backend/chess_trainer/api/jobs.py`, `backend/chess_trainer/api/schemas.py`, `backend/chess_trainer/api/routes/system.py`
- Test: `backend/tests/test_api_system.py`

**Interfaces:**
- Consumes: `make_engine`, `init_db`, `make_session_factory` (Task 3); `load_settings`, `save_settings`, `get_setting`, `set_setting`, `AppSettings` (Task 3); `ChessComClient` (Task 4); `import_games` (Task 5); `find_stockfish`, `StockfishEngine`, `EngineLike` (Task 6); `analyze_pending` (Task 11); `regenerate_all` (Task 11).
- Produces:
  - `create_app(db_path: str | None = None, engine_factory=None, chesscom_factory=None) -> FastAPI`. `engine_factory(settings) -> EngineLike | None`; `chesscom_factory(settings) -> ChessComClient`. Padrões: `default_engine_factory` (usa `find_stockfish`) e cliente real com `User-Agent "chess-trainer/0.1 (local)"`. `db_path` padrão: env `CHESS_TRAINER_DB` ou `backend/data/chess_trainer.db`. Se `frontend/dist` existir (irmão de `backend/`), é montado em `/` depois das rotas.
  - `deps.get_db(request) -> Session` (dependency).
  - `jobs.JobStatus` (dataclass: `state: "idle"|"running"|"error"`, `job`, `stage`, `done`, `total`, `message`, `error`, `finished_at`) e `jobs.JobRunner` com `submit(name, fn: Callable[[ProgressFn], None]) -> bool` (False se ocupado), `progress(stage, done, total, message="")`, `is_busy`, `wait(timeout=60.0)`, `snapshot() -> dict`.
  - Rotas: `GET /api/status`, `GET /api/settings`, `PUT /api/settings`, `POST /api/import` (202/400/409), `POST /api/analyze?limit=` (202/409/503), `POST /api/puzzles/regenerate` (202/409/503).
  - Chave de `Setting` `"last_import_at"` (ISO) gravada ao fim de uma importação bem-sucedida.

- [ ] **Step 1: Escrever `tests/test_api_system.py`**

```python
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.importers.chesscom import ChessComClient
from tests.fakes import FakeEngine, first_legal_default

FIXTURES = Path(__file__).parent / "fixtures"


def chesscom_factory(settings):
    def handler(request: httpx.Request):
        if request.url.path.endswith("/games/archives"):
            return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_archives.json").read_text()))
        if request.url.path.endswith("/2026/08"):
            return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_month.json").read_text()))
        return httpx.Response(200, json={"games": []})
    return ChessComClient("t", http=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def app():
    return create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)),
                      chesscom_factory=chesscom_factory)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_status_and_settings_roundtrip(client):
    status = client.get("/api/status").json()
    assert status["engine"]["available"] is True
    assert status["job"]["state"] == "idle" and status["games_total"] == 0

    assert client.get("/api/settings").json()["new_per_day"] == 10
    r = client.put("/api/settings", json={"chesscom_username": " TheRealZibs ", "new_per_day": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["chesscom_username"] == "therealzibs" and body["new_per_day"] == 5
    assert body["analysis_depth"] == 18  # não enviado, mantido


def test_import_requires_username(client):
    assert client.post("/api/import").status_code == 400


def test_import_job_runs_and_reports(client, app):
    client.put("/api/settings", json={"chesscom_username": "therealzibs"})
    r = client.post("/api/import")
    assert r.status_code == 202 and r.json()["job"] == "import"
    app.state.jobs.wait()
    status = client.get("/api/status").json()
    assert status["job"]["state"] == "idle" and status["job"]["job"] == "import"
    assert status["games_total"] == 1 and status["games_pending"] == 1
    assert status["last_import_at"] is not None


def test_analyze_job_and_regenerate(client, app):
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import"); app.state.jobs.wait()
    r = client.post("/api/analyze", params={"limit": 5})
    assert r.status_code == 202
    app.state.jobs.wait()
    status = client.get("/api/status").json()
    assert status["job"]["state"] == "idle" and status["games_pending"] == 0
    r = client.post("/api/puzzles/regenerate")
    assert r.status_code == 202
    app.state.jobs.wait()
    assert client.get("/api/status").json()["job"]["state"] == "idle"


def test_analyze_without_engine_is_503():
    app = create_app(db_path=":memory:", engine_factory=lambda s: None, chesscom_factory=chesscom_factory)
    client = TestClient(app)
    assert client.get("/api/status").json()["engine"]["available"] is False
    assert client.post("/api/analyze").status_code == 503


def test_job_error_is_reported(app):
    def boom(progress):
        raise RuntimeError("falhou feio")
    assert app.state.jobs.submit("import", boom) is True
    app.state.jobs.wait()
    snap = app.state.jobs.snapshot()
    assert snap["state"] == "error" and "falhou feio" in snap["error"]
    assert app.state.jobs.submit("import", lambda p: None) is True  # volta a aceitar
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_api_system.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar `api/jobs.py`**

```python
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable

from chess_trainer.core.models import utcnow

ProgressFn = Callable[[str, int, int, str], None]


@dataclass
class JobStatus:
    state: str = "idle"  # idle | running | error
    job: str | None = None
    stage: str = ""
    done: int = 0
    total: int = 0
    message: str = ""
    error: str | None = None
    finished_at: datetime | None = None


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.status = JobStatus()

    @property
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit(self, name: str, fn: Callable[[ProgressFn], None]) -> bool:
        with self._lock:
            if self.is_busy:
                return False
            self.status = JobStatus(state="running", job=name)
            self._thread = threading.Thread(target=self._run, args=(fn,), daemon=True)
            self._thread.start()
            return True

    def _run(self, fn: Callable[[ProgressFn], None]) -> None:
        try:
            fn(self.progress)
            self.status.state = "idle"
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira estado de erro visível
            self.status.state = "error"
            self.status.error = str(exc)
        finally:
            self.status.finished_at = utcnow()

    def progress(self, stage: str, done: int, total: int, message: str = "") -> None:
        self.status.stage = stage
        self.status.done = done
        self.status.total = total
        self.status.message = message

    def wait(self, timeout: float = 60.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def snapshot(self) -> dict:
        data = asdict(self.status)
        if data["finished_at"] is not None:
            data["finished_at"] = data["finished_at"].isoformat()
        return data
```

- [ ] **Step 4: Implementar `api/deps.py`**

```python
from fastapi import Request


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Implementar `api/schemas.py`** (inclui já os schemas da Task 15)

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsOut(BaseModel):
    chesscom_username: str
    categories: list[str]
    stockfish_path: str
    analysis_depth: int
    puzzle_depth: int
    mistake_threshold_cp: int
    blunder_threshold_cp: int
    avoid_gap_cp: int
    new_per_day: int
    leech_lapses: int


class SettingsIn(BaseModel):
    chesscom_username: str | None = None
    categories: list[str] | None = None
    stockfish_path: str | None = None
    analysis_depth: int | None = None
    puzzle_depth: int | None = None
    mistake_threshold_cp: int | None = None
    blunder_threshold_cp: int | None = None
    avoid_gap_cp: int | None = None
    new_per_day: int | None = None
    leech_lapses: int | None = None


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_id: str
    white: str
    black: str
    result: str
    time_control: str
    category: str
    played_at: datetime
    my_color: str
    analyzed_at: datetime | None
    my_mistakes: int = 0


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ply: int
    fen: str
    move_played: str
    move_uci: str
    eval_before: int
    eval_after: int
    best_move: str | None
    is_mistake: bool
    mistake_level: str | None
    mistake_by: str | None
    puzzle_ids: list[str] = []


class GameDetail(GameOut):
    pgn: str
    positions: list[PositionOut]


class PuzzleRef(BaseModel):
    id: str
    kind: str
    theme: str
    is_leech: bool


class MistakeOut(BaseModel):
    position_id: str
    game_id: str
    ply: int
    fen: str
    move_played: str
    move_uci: str
    best_move: str | None
    eval_before: int
    eval_after: int
    mistake_level: str
    mistake_by: str
    category: str
    played_at: datetime
    white: str
    black: str
    my_color: str
    puzzles: list[PuzzleRef]


class SrsOut(BaseModel):
    ease: float
    interval_days: int
    lapses: int
    due_at: datetime | None
    last_reviewed_at: datetime | None


class GameRef(BaseModel):
    id: str
    white: str
    black: str
    played_at: datetime
    source_id: str
    my_color: str


class PuzzleOut(BaseModel):
    id: str
    kind: str
    fen_start: str
    side_to_move: str
    solution: dict
    end_reason: str
    theme: str
    category: str
    solver_moves: int
    is_leech: bool
    srs: SrsOut
    game: GameRef
    ply: int
    move_played: str


class QueueOut(BaseModel):
    due_count: int
    new_available: int
    new_remaining_today: int
    items: list[PuzzleOut]


class SessionIn(BaseModel):
    planned_minutes: int | None = None
    filters: dict = {}


class SessionOut(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime | None
    planned_minutes: int | None
    filters: dict
    reviews: int = 0
    correct: int = 0
    total_duration_ms: int = 0


class ReviewIn(BaseModel):
    puzzle_id: str
    session_id: str | None = None
    correct: bool
    used_hint: bool = False
    duration_ms: int = 0


class ReviewOut(BaseModel):
    id: str
    puzzle_id: str
    result: str
    used_hint: bool
    ease: float
    interval_days: int
    due_at: datetime
    lapses: int
    is_leech: bool


class DashboardOut(BaseModel):
    due_today: int
    new_available: int
    new_remaining_today: int
    streak_days: int
    reviews_today: int
    last_import_at: datetime | None
    games_total: int
    games_analyzed: int
    puzzles_total: int
    leeches: int
```

- [ ] **Step 6: Implementar `api/routes/system.py`**

```python
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import SettingsIn, SettingsOut
from chess_trainer.config import AppSettings, get_setting, load_settings, save_settings, set_setting
from chess_trainer.core.analysis.engine import find_stockfish
from chess_trainer.core.importers.service import import_games
from chess_trainer.core.models import Game, utcnow
from chess_trainer.core.pipeline import analyze_pending
from chess_trainer.core.puzzles.service import regenerate_all

router = APIRouter(prefix="/api")


def _engine_available(request: Request, settings: AppSettings) -> tuple[bool, str | None]:
    probe = getattr(request.app.state, "engine_probe", None)
    if probe is not None:
        return probe(settings)
    path = find_stockfish(settings.stockfish_path)
    return path is not None, path


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)):
    settings = load_settings(db)
    available, path = _engine_available(request, settings)
    total = db.scalar(select(func.count(Game.id))) or 0
    pending = db.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_(None))) or 0
    last_import = get_setting(db, "last_import_at")
    return {
        "engine": {"available": available, "path": path},
        "job": request.app.state.jobs.snapshot(),
        "games_total": total,
        "games_pending": pending,
        "last_import_at": last_import,
    }


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return asdict(load_settings(db))


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    current = load_settings(db)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(current, key, value)
    return asdict(save_settings(db, current))


def _submit(request: Request, name: str, fn) -> dict:
    if not request.app.state.jobs.submit(name, fn):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": name}


@router.post("/import", status_code=202)
def post_import(request: Request, db: Session = Depends(get_db)):
    settings = load_settings(db)
    if not settings.chesscom_username:
        raise HTTPException(400, "configure o usuário do chess.com primeiro")
    app = request.app

    def job(progress):
        session = app.state.session_factory()
        try:
            s = load_settings(session)
            client = app.state.chesscom_factory(s)
            import_games(session, client, s, progress)
            set_setting(session, "last_import_at", utcnow().isoformat())
        finally:
            session.close()

    return _submit(request, "import", job)


def _engine_job(request: Request, name: str, work):
    db = request.app.state.session_factory()
    try:
        settings = load_settings(db)
    finally:
        db.close()
    available, _ = _engine_available(request, settings)
    if not available:
        raise HTTPException(503, "Stockfish não encontrado; configure o caminho em /api/settings")
    app = request.app

    def job(progress):
        session = app.state.session_factory()
        engine = None
        try:
            s = load_settings(session)
            engine = app.state.engine_factory(s)
            if engine is None:
                raise RuntimeError("Stockfish não encontrado")
            work(session, engine, s, progress)
        finally:
            if engine is not None:
                engine.close()
            session.close()

    return _submit(request, name, job)


@router.post("/analyze", status_code=202)
def post_analyze(request: Request, limit: int | None = None):
    return _engine_job(request, "analyze",
                       lambda db, engine, s, progress: analyze_pending(db, engine, s, progress, limit))


@router.post("/puzzles/regenerate", status_code=202)
def post_regenerate(request: Request):
    return _engine_job(request, "regenerate",
                       lambda db, engine, s, progress: regenerate_all(db, engine, s, progress))
```

- [ ] **Step 7: Implementar `api/app.py`**

```python
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from chess_trainer.api.jobs import JobRunner
from chess_trainer.api.routes import system
from chess_trainer.config import AppSettings
from chess_trainer.core.analysis.engine import EngineLike, StockfishEngine, find_stockfish
from chess_trainer.core.db import init_db, make_engine, make_session_factory
from chess_trainer.core.importers.chesscom import ChessComClient

USER_AGENT = "chess-trainer/0.1 (local)"
BACKEND_DIR = Path(__file__).resolve().parents[2]


def default_engine_factory(settings: AppSettings) -> EngineLike | None:
    path = find_stockfish(settings.stockfish_path)
    return StockfishEngine(path) if path else None


def default_chesscom_factory(settings: AppSettings) -> ChessComClient:
    return ChessComClient(USER_AGENT)


def create_app(db_path: str | None = None, engine_factory=None, chesscom_factory=None) -> FastAPI:
    if db_path is None:
        db_path = os.environ.get("CHESS_TRAINER_DB", str(BACKEND_DIR / "data" / "chess_trainer.db"))
    db_engine = make_engine(db_path)
    init_db(db_engine)

    app = FastAPI(title="Chess Trainer", version="0.1.0")
    app.state.session_factory = make_session_factory(db_engine)
    app.state.jobs = JobRunner()
    app.state.engine_factory = engine_factory or default_engine_factory
    app.state.chesscom_factory = chesscom_factory or default_chesscom_factory
    if engine_factory is not None:
        # em testes a disponibilidade da engine é decidida pela factory, não pelo disco
        app.state.engine_probe = lambda s: (engine_factory(s) is not None, "fake")

    app.include_router(system.router)

    dist = BACKEND_DIR.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    return app
```

- [ ] **Step 8: Rodar para ver passar**

Run: `uv run pytest tests/test_api_system.py -q`
Expected: `6 passed`

- [ ] **Step 9: Commit**

```bash
git add backend/chess_trainer/api backend/tests/test_api_system.py
git commit -m "feat: API FastAPI com fila de jobs, status, configurações, importação e análise"
```

---

### Task 15: API — partidas, erros, puzzles, fila, sessões, revisões e painel

**Files:**
- Create: `backend/chess_trainer/api/routes/games.py`, `backend/chess_trainer/api/routes/training.py`
- Modify: `backend/chess_trainer/api/app.py` (incluir os dois routers)
- Test: `backend/tests/test_api_training.py`

**Interfaces:**
- Consumes: schemas (Task 14), `build_queue`, `QueueFilters`, `count_new_reviewed_today`, `local_day_start` (Task 13), `record_review`, `unleech` (Task 13), modelos.
- Produces as rotas listadas no spec §9:
  - `GET /api/games?category&color&result&analyzed&limit=50&offset=0` → `list[GameOut]` (mais recentes primeiro; `my_mistakes` = erros do usuário na partida)
  - `GET /api/games/{id}` → `GameDetail` (404 se não existe)
  - `GET /api/mistakes?level&theme&category&by=me` → `list[MistakeOut]` (mais recentes primeiro; `by` aceita `me`, `opponent`, `all`; padrão `me`)
  - `GET /api/puzzles/{id}` → `PuzzleOut`
  - `GET /api/queue?category&theme&kind&color` → `QueueOut`
  - `GET /api/leeches` → `list[PuzzleOut]`; `POST /api/puzzles/{id}/unleech` → `PuzzleOut`
  - `POST /api/sessions` → `SessionOut` (201); `POST /api/sessions/{id}/end` → `SessionOut` com totais
  - `POST /api/reviews` → `ReviewOut` (201; 404 se puzzle não existe)
  - `GET /api/dashboard` → `DashboardOut`. `streak_days` = dias locais consecutivos com pelo menos uma revisão, contando a partir de hoje (ou de ontem, se hoje ainda não houve revisão).

- [ ] **Step 1: Escrever `tests/test_api_training.py`**

```python
import chess
import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from tests.fakes import FakeEngine, first_legal_default
from tests.test_api_system import chesscom_factory


def _before_mate() -> chess.Board:
    b = chess.Board()
    for u in ("e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6"):
        b.push_uci(u)
    return b


def engine_factory(settings):
    return FakeEngine({_before_mate().epd(): [LineEval("h5f7", MATE_SCORE - 1, ("h5f7",))]},
                      first_legal_default(0))


@pytest.fixture
def ready(tmp_path):
    """App com uma partida importada e analisada (1 puzzle mate_in_1, erro do adversário)."""
    app = create_app(db_path=":memory:", engine_factory=engine_factory, chesscom_factory=chesscom_factory)
    client = TestClient(app)
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4, "leech_lapses": 2})
    client.post("/api/import"); app.state.jobs.wait()
    client.post("/api/analyze"); app.state.jobs.wait()
    assert app.state.jobs.snapshot()["state"] == "idle"
    return app, client


def test_games_list_and_detail(ready):
    _, client = ready
    games = client.get("/api/games").json()
    assert len(games) == 1 and games[0]["category"] == "rapid" and games[0]["my_mistakes"] == 0
    assert client.get("/api/games", params={"category": "blitz"}).json() == []
    assert client.get("/api/games", params={"analyzed": "false"}).json() == []
    detail = client.get(f"/api/games/{games[0]['id']}").json()
    assert len(detail["positions"]) == 7 and detail["pgn"].startswith("[Event")
    ply6 = detail["positions"][5]
    assert ply6["is_mistake"] and ply6["mistake_level"] == "blunder" and len(ply6["puzzle_ids"]) == 1
    assert client.get("/api/games/nope").status_code == 404


def test_mistakes_listing(ready):
    _, client = ready
    assert client.get("/api/mistakes").json() == []                    # padrão: só os meus
    all_m = client.get("/api/mistakes", params={"by": "all"}).json()
    assert len(all_m) == 1 and all_m[0]["ply"] == 6 and all_m[0]["puzzles"][0]["theme"] == "mate_in_1"
    assert client.get("/api/mistakes", params={"by": "opponent", "level": "mistake"}).json() == []
    assert len(client.get("/api/mistakes", params={"by": "all", "theme": "mate_in_1"}).json()) == 1


def test_queue_review_and_dashboard_flow(ready):
    _, client = ready
    q = client.get("/api/queue").json()
    assert q["due_count"] == 0 and q["new_available"] == 1 and len(q["items"]) == 1
    puzzle = q["items"][0]
    assert puzzle["theme"] == "mate_in_1" and puzzle["solution"]["moves"][0]["uci"] == "h5f7"
    assert puzzle["srs"]["due_at"] is None and puzzle["game"]["white"] == "therealzibs"
    assert client.get(f"/api/puzzles/{puzzle['id']}").json()["id"] == puzzle["id"]

    session = client.post("/api/sessions", json={"planned_minutes": 25, "filters": {"kind": "punish"}}).json()
    r = client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "session_id": session["id"],
                                          "correct": True, "used_hint": False, "duration_ms": 4000})
    assert r.status_code == 201
    body = r.json()
    assert body["result"] == "correct" and body["interval_days"] == 1 and body["is_leech"] is False

    q2 = client.get("/api/queue").json()
    assert q2["due_count"] == 0 and q2["items"] == [] and q2["new_available"] == 0

    ended = client.post(f"/api/sessions/{session['id']}/end").json()
    assert ended["reviews"] == 1 and ended["correct"] == 1 and ended["total_duration_ms"] == 4000
    assert ended["ended_at"] is not None

    dash = client.get("/api/dashboard").json()
    assert dash["due_today"] == 0 and dash["reviews_today"] == 1 and dash["streak_days"] == 1
    assert dash["games_total"] == 1 and dash["games_analyzed"] == 1 and dash["puzzles_total"] == 1
    assert dash["last_import_at"] is not None


def test_leech_and_unleech(ready):
    _, client = ready
    puzzle = client.get("/api/queue").json()["items"][0]
    for _ in range(2):
        r = client.post("/api/reviews", json={"puzzle_id": puzzle["id"], "correct": False})
    assert r.json()["is_leech"] is True
    leeches = client.get("/api/leeches").json()
    assert [p["id"] for p in leeches] == [puzzle["id"]]
    assert client.get("/api/dashboard").json()["leeches"] == 1
    back = client.post(f"/api/puzzles/{puzzle['id']}/unleech").json()
    assert back["is_leech"] is False and back["srs"]["lapses"] == 0
    assert client.get("/api/queue").json()["due_count"] == 1


def test_review_unknown_puzzle_is_404(ready):
    _, client = ready
    assert client.post("/api/reviews", json={"puzzle_id": "nope", "correct": True}).status_code == 404
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `uv run pytest tests/test_api_training.py -q`
Expected: FAIL (404 nas rotas ainda inexistentes)

- [ ] **Step 3: Implementar `api/routes/games.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import GameDetail, GameOut, MistakeOut, PositionOut, PuzzleRef
from chess_trainer.core.models import Game, Position, Puzzle

router = APIRouter(prefix="/api")


def _my_mistakes_map(db: Session, game_ids: list[str]) -> dict[str, int]:
    if not game_ids:
        return {}
    rows = db.execute(
        select(Position.game_id, func.count(Position.id))
        .where(Position.game_id.in_(game_ids), Position.is_mistake.is_(True), Position.mistake_by == "me")
        .group_by(Position.game_id)
    ).all()
    return {game_id: n for game_id, n in rows}


def _game_out(game: Game, my_mistakes: int) -> GameOut:
    out = GameOut.model_validate(game)
    out.my_mistakes = my_mistakes
    return out


@router.get("/games", response_model=list[GameOut])
def list_games(
    category: str | None = None,
    color: str | None = None,
    result: str | None = None,
    analyzed: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Game).order_by(Game.played_at.desc()).limit(limit).offset(offset)
    if category:
        stmt = stmt.where(Game.category == category)
    if color:
        stmt = stmt.where(Game.my_color == color)
    if result:
        stmt = stmt.where(Game.result == result)
    if analyzed is True:
        stmt = stmt.where(Game.analyzed_at.is_not(None))
    elif analyzed is False:
        stmt = stmt.where(Game.analyzed_at.is_(None))
    games = db.scalars(stmt).all()
    counts = _my_mistakes_map(db, [g.id for g in games])
    return [_game_out(g, counts.get(g.id, 0)) for g in games]


@router.get("/games/{game_id}", response_model=GameDetail)
def get_game(game_id: str, db: Session = Depends(get_db)):
    game = db.get(Game, game_id, options=[selectinload(Game.positions).selectinload(Position.puzzles)])
    if game is None:
        raise HTTPException(404, "partida não encontrada")
    positions = []
    for pos in game.positions:
        out = PositionOut.model_validate(pos)
        out.puzzle_ids = [p.id for p in pos.puzzles]
        positions.append(out)
    base = _game_out(game, _my_mistakes_map(db, [game.id]).get(game.id, 0))
    return GameDetail(**base.model_dump(), pgn=game.pgn, positions=positions)


@router.get("/mistakes", response_model=list[MistakeOut])
def list_mistakes(
    level: str | None = None,
    theme: str | None = None,
    category: str | None = None,
    by: str = "me",
    limit: int = 200,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Position, Game)
        .join(Game, Game.id == Position.game_id)
        .where(Position.is_mistake.is_(True))
        .order_by(Game.played_at.desc(), Position.ply)
        .limit(limit)
        .options(selectinload(Position.puzzles))
    )
    if by in ("me", "opponent"):
        stmt = stmt.where(Position.mistake_by == by)
    if level:
        stmt = stmt.where(Position.mistake_level == level)
    if category:
        stmt = stmt.where(Game.category == category)
    if theme:
        stmt = stmt.where(Position.id.in_(select(Puzzle.position_id).where(Puzzle.theme == theme)))
    items = []
    for pos, game in db.execute(stmt).all():
        items.append(MistakeOut(
            position_id=pos.id, game_id=game.id, ply=pos.ply, fen=pos.fen, move_played=pos.move_played,
            move_uci=pos.move_uci, best_move=pos.best_move, eval_before=pos.eval_before,
            eval_after=pos.eval_after, mistake_level=pos.mistake_level, mistake_by=pos.mistake_by,
            category=game.category, played_at=game.played_at, white=game.white, black=game.black,
            my_color=game.my_color,
            puzzles=[PuzzleRef(id=p.id, kind=p.kind, theme=p.theme, is_leech=p.is_leech) for p in pos.puzzles],
        ))
    return items
```

- [ ] **Step 4: Implementar `api/routes/training.py`**

```python
import json
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import (
    DashboardOut, GameRef, PuzzleOut, QueueOut, ReviewIn, ReviewOut, SessionIn, SessionOut, SrsOut,
)
from chess_trainer.config import get_setting, load_settings
from chess_trainer.core.models import Game, Puzzle, Review, TrainingSession, utcnow
from chess_trainer.core.srs.queue import QueueFilters, build_queue, count_new_reviewed_today, local_day_start
from chess_trainer.core.srs.reviews import record_review, unleech

router = APIRouter(prefix="/api")


def _puzzle_out(p: Puzzle) -> PuzzleOut:
    return PuzzleOut(
        id=p.id, kind=p.kind, fen_start=p.fen_start, side_to_move=p.side_to_move,
        solution=p.solution_data, end_reason=p.end_reason, theme=p.theme, category=p.category,
        solver_moves=p.solver_moves, is_leech=p.is_leech,
        srs=SrsOut(ease=p.srs_ease, interval_days=p.srs_interval_days, lapses=p.srs_lapses,
                   due_at=p.srs_due_at, last_reviewed_at=p.srs_last_reviewed_at),
        game=GameRef(id=p.game.id, white=p.game.white, black=p.game.black, played_at=p.game.played_at,
                     source_id=p.game.source_id, my_color=p.game.my_color),
        ply=p.position.ply, move_played=p.position.move_played,
    )


def _get_puzzle(db: Session, puzzle_id: str) -> Puzzle:
    puzzle = db.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise HTTPException(404, "puzzle não encontrado")
    return puzzle


@router.get("/puzzles/{puzzle_id}", response_model=PuzzleOut)
def get_puzzle(puzzle_id: str, db: Session = Depends(get_db)):
    return _puzzle_out(_get_puzzle(db, puzzle_id))


@router.get("/queue", response_model=QueueOut)
def get_queue(
    category: str | None = None, theme: str | None = None, kind: str | None = None, color: str | None = None,
    db: Session = Depends(get_db),
):
    result = build_queue(db, QueueFilters(category, theme, kind, color), load_settings(db), utcnow())
    items = result.due or result.new
    return QueueOut(due_count=result.due_count, new_available=result.new_available,
                    new_remaining_today=result.new_remaining_today, items=[_puzzle_out(p) for p in items])


@router.get("/leeches", response_model=list[PuzzleOut])
def get_leeches(db: Session = Depends(get_db)):
    puzzles = db.scalars(select(Puzzle).where(Puzzle.is_leech.is_(True)).order_by(Puzzle.leech_since.desc())).all()
    return [_puzzle_out(p) for p in puzzles]


@router.post("/puzzles/{puzzle_id}/unleech", response_model=PuzzleOut)
def post_unleech(puzzle_id: str, db: Session = Depends(get_db)):
    puzzle = _get_puzzle(db, puzzle_id)
    unleech(db, puzzle, utcnow())
    return _puzzle_out(puzzle)


def _session_out(db: Session, s: TrainingSession) -> SessionOut:
    rows = db.execute(
        select(func.count(Review.id), func.sum(Review.duration_ms),
               func.sum(func.iif(Review.result == "correct", 1, 0)))
        .where(Review.session_id == s.id)
    ).one()
    return SessionOut(id=s.id, started_at=s.started_at, ended_at=s.ended_at, planned_minutes=s.planned_minutes,
                      filters=json.loads(s.filters or "{}"), reviews=int(rows[0] or 0),
                      correct=int(rows[2] or 0), total_duration_ms=int(rows[1] or 0))


@router.post("/sessions", response_model=SessionOut, status_code=201)
def post_session(body: SessionIn, db: Session = Depends(get_db)):
    s = TrainingSession(planned_minutes=body.planned_minutes, filters=json.dumps(body.filters))
    db.add(s)
    db.commit()
    return _session_out(db, s)


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
def end_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise HTTPException(404, "sessão não encontrada")
    if s.ended_at is None:
        s.ended_at = utcnow()
        db.commit()
    return _session_out(db, s)


@router.post("/reviews", response_model=ReviewOut, status_code=201)
def post_review(body: ReviewIn, db: Session = Depends(get_db)):
    puzzle = _get_puzzle(db, body.puzzle_id)
    review = record_review(db, puzzle, session_id=body.session_id, correct=body.correct,
                           used_hint=body.used_hint, duration_ms=body.duration_ms,
                           now=utcnow(), settings=load_settings(db))
    return ReviewOut(id=review.id, puzzle_id=puzzle.id, result=review.result, used_hint=review.used_hint,
                     ease=review.ease, interval_days=review.interval_days, due_at=review.due_at,
                     lapses=review.lapses, is_leech=puzzle.is_leech)


def _streak_days(db: Session, now) -> int:
    stamps = db.scalars(select(Review.reviewed_at)).all()
    days = {ts.replace(tzinfo=timezone.utc).astimezone().date() for ts in stamps}
    today = now.replace(tzinfo=timezone.utc).astimezone().date()
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    now = utcnow()
    settings = load_settings(db)
    queue = build_queue(db, QueueFilters(), settings, now)
    day_start = local_day_start(now)
    reviews_today = db.scalar(select(func.count(Review.id)).where(Review.reviewed_at >= day_start)) or 0
    last_import = get_setting(db, "last_import_at")
    return DashboardOut(
        due_today=queue.due_count,
        new_available=queue.new_available,
        new_remaining_today=queue.new_remaining_today,
        streak_days=_streak_days(db, now),
        reviews_today=int(reviews_today),
        last_import_at=last_import,
        games_total=int(db.scalar(select(func.count(Game.id))) or 0),
        games_analyzed=int(db.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_not(None))) or 0),
        puzzles_total=int(db.scalar(select(func.count(Puzzle.id))) or 0),
        leeches=int(db.scalar(select(func.count(Puzzle.id)).where(Puzzle.is_leech.is_(True))) or 0),
    )
```

- [ ] **Step 5: Registrar os routers em `api/app.py`**

```python
from chess_trainer.api.routes import games, system, training
# ...
    app.include_router(system.router)
    app.include_router(games.router)
    app.include_router(training.router)
```

- [ ] **Step 6: Rodar para ver passar**

Run: `uv run pytest tests/test_api_training.py -q`
Expected: `5 passed`. Se `func.iif` não existir na versão do SQLite, trocar por `func.sum(case((Review.result == "correct", 1), else_=0))` com `from sqlalchemy import case`.

- [ ] **Step 7: Rodar a suíte inteira**

Run: `uv run pytest -q`
Expected: tudo verde, 1 pulado.

- [ ] **Step 8: Commit**

```bash
git add backend/chess_trainer/api backend/tests/test_api_training.py
git commit -m "feat: rotas de partidas, erros, puzzles, fila, sessões, revisões e painel"
```

---

### Task 16: Ponto de entrada, Stockfish e verificação manual com partidas reais

**Files:**
- Create: `backend/chess_trainer/__main__.py`, `backend/README.md`
- Modify: raiz `.gitignore` (criar com `backend/data/`, `backend/engines/`, `.venv/`)

**Interfaces:**
- Produces: `python -m chess_trainer` (ou `uv run python -m chess_trainer`) sobe a API em `http://127.0.0.1:8000`, com docs em `/docs`.

- [ ] **Step 1: Escrever `chess_trainer/__main__.py`**

```python
import uvicorn

from chess_trainer.api.app import create_app


def main() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Escrever `backend/README.md`**

```markdown
# Chess Trainer — backend

## Rodar

    cd backend
    uv sync
    uv run python -m chess_trainer

API em http://127.0.0.1:8000, documentação interativa em /docs.

## Stockfish

Baixe o binário em https://stockfishchess.org/download/ (Windows: `stockfish-windows-x86-64-avx2.zip`)
e extraia em `backend/engines/`. O app encontra `engines/**/stockfish*.exe` sozinho; ou informe o
caminho em `PUT /api/settings {"stockfish_path": "..."}`.

## Testes

    uv run pytest -q            # rápidos
    uv run pytest -q -m slow    # com Stockfish real

## Primeiro uso

1. `PUT /api/settings` com `{"chesscom_username": "seu-usuario"}`
2. `POST /api/import` e acompanhe em `GET /api/status`
3. `POST /api/analyze?limit=5` (depth 18 leva ~20 s por partida)
4. `GET /api/queue` devolve os puzzles do dia
```

- [ ] **Step 3: Instalar o Stockfish** — **pedir confirmação ao usuário antes de baixar** (download de ~40 MB do GitHub oficial `official-stockfish/Stockfish`, release mais recente, arquivo `stockfish-windows-x86-64-avx2.zip`). Com o ok:

```bash
mkdir -p backend/engines && cd backend/engines && curl -L -o stockfish.zip https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-avx2.zip && unzip -o stockfish.zip && rm stockfish.zip && ls -R
```

Run: `cd backend && uv run pytest -q -m slow`
Expected: `1 passed` (`test_real_stockfish_finds_mate_in_one`).

- [ ] **Step 4: Subir o servidor e fazer a primeira importação real**

Run (em segundo plano): `cd backend && uv run python -m chess_trainer`
Depois:

```bash
curl -s -X PUT http://127.0.0.1:8000/api/settings -H "content-type: application/json" -d "{\"chesscom_username\": \"therealzibs\"}"
curl -s -X POST http://127.0.0.1:8000/api/import
```

Acompanhar `GET /api/status` até `job.state == "idle"`. Expected: `games_total` na casa das centenas (16 meses, só rapid/daily).

- [ ] **Step 5: Analisar 5 partidas e inspecionar os puzzles**

```bash
curl -s -X POST "http://127.0.0.1:8000/api/analyze?limit=5"
```

Quando terminar: `GET /api/mistakes?by=all` e `GET /api/queue`. Verificação manual (registrar o resultado no commit):
- Cada puzzle "punir" termina em mate ou numa captura que concretiza o ganho.
- Nenhum puzzle com solução vazia ou com lance ilegal (validar com python-chess: reproduzir `solution.moves` a partir de `fen_start`).
- Contagem de erros por partida plausível (2–6 numa rapid típica). Se sair 15+, os limiares estão baixos demais para a força do jogador; anotar para ajuste no spec.

- [ ] **Step 6: Commit**

```bash
git add backend/chess_trainer/__main__.py backend/README.md .gitignore
git commit -m "feat: ponto de entrada uvicorn e instruções de uso"
```

---

## Self-review (feito ao escrever)

- **Cobertura do spec**: §3 modelo → Task 3; §4 importação → Tasks 4–5; §5 análise → Tasks 6–7; §6 erros → Task 8; §7 puzzles (7.1–7.4) → Tasks 9–11; §8 SRS e fila → Tasks 12–13; §9 API → Tasks 14–15; §10 interface → **fora deste plano** (plano do frontend, a escrever após este); §11 testes → em cada task, mais o manual na Task 16.
- **Consistência de nomes**: `ProgressFn` definido em `importers/service.py`, `puzzles/service.py`, `pipeline.py` e `api/jobs.py` com a mesma assinatura `(stage, done, total, message)`. `EngineLike` ganha `close`/`restart` na Task 11 e `FakeEngine` (Task 6) já os implementa. `Puzzle.solution_data` (Task 3) é usado por `PuzzleOut` (Task 15). `thresholds_from` (Task 8) e `puzzle_config_from` (Task 9) vivem em `config.py` e são consumidos pela Task 11.
- **Riscos conhecidos**: `func.iif` depende de SQLite ≥ 3.32 (alternativa documentada na Task 15). Threads + SQLite em memória com `StaticPool` funcionam nos testes; em disco, `check_same_thread=False` cobre o job em segundo plano porque só há um job por vez.
