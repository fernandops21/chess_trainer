# Táticas do Lichess e estatísticas por tema — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar o banco aberto de puzzles do Lichess, treinar "táticas" calibradas por rating e tema no mesmo tabuleiro dos puzzles próprios, e mostrar estatísticas de acerto por tema.

**Architecture:** Backend ganha o pacote `chess_trainer/core/tactics/` (importador em streaming do CSV `.zst`, conversão de linha em puzzle jogável, seleção por janela de rating/tema, rating Elo do usuário) e `core/stats.py` (acerto por tema cruzando `Review` e `TacticsAttempt`), expostos em `api/routes/tactics.py`. Frontend generaliza `usePuzzle`/`PuzzleView` para um `Trainable` (puzzle próprio ou tática), adiciona a fonte "Táticas do Lichess" na tela Treinar com fila infinita, e cartões novos no Painel e nas Configurações.

**Tech Stack:** Python 3.13 (`uv`), FastAPI, SQLAlchemy 2.0 + SQLite, `zstandard`, `httpx`, python-chess, pytest; React 19 + TypeScript, TanStack Query, chess.js, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-05-taticas-lichess-design.md`

## Global Constraints

- Texto de interface em português do Brasil. Nunca usar "regerar/regeração"; usar "recriar/recriação". A palavra para o banco é "táticas" (não "puzzles do Lichess" em botões).
- Convenção de datas: `utcnow()` naive UTC (`core/models.py`); "hoje" via `local_day_start` (`core/srs/queue.py`).
- Trabalho pesado (download, parse do CSV) roda no `JobRunner` (`api/jobs.py`), nunca no request; cancelamento via `should_stop()` entre lotes; nunca segurar uma transação de escrita durante I/O de rede.
- Toda escrita nova no SQLite em lotes; `INSERT OR IGNORE` para idempotência.
- Nenhum download em testes: o job recebe a fonte por `app.state.tactics_source` (caminho local ou URL).
- Backend: `cd backend && uv run pytest -q` deve ficar verde (hoje 172 passam; 2 warnings do Starlette/anyio são conhecidos). Frontend: `cd frontend && npm test -- --run` e `npm run build` verdes (44 testes hoje).
- Commits em português, conventional (`feat:`, `test:`, `fix:`), com trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- `usePuzzle` mantém o contrato "uma instância por puzzle, remontar com `key={puzzle.id}`".
- Rating do usuário: Elo simplificado, K = 32, acerto sem dica = 1, resto = 0; inicial 1200 (`tactics_rating`).
- Formato do CSV do Lichess: `PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags`; `Moves[0]` é o lance do adversário, aplicado antes do puzzle começar.

---

## File map

Backend (`backend/chess_trainer/`):
- Modify `core/models.py` — `LichessPuzzle`, `LichessPuzzleTheme`, `TacticsAttempt`.
- Modify `config.py` — `tactics_rating`, `tactics_window`, `lichess_min_plays`, `lichess_min_popularity`.
- Modify `api/schemas.py` — settings novos, `TacticOut`, `AttemptIn/Out`, `TacticsStatusOut`, `ThemeCountOut`, `ThemeStatOut`.
- Create `core/tactics/__init__.py`, `core/tactics/themes.py` (mapa PT + prioridade), `core/tactics/convert.py` (`Tactic`, `to_tactic`), `core/tactics/rating.py` (`elo_update`), `core/tactics/importer.py` (`parse_rows`, `import_csv_zst`, `download_file`), `core/tactics/service.py` (`pick_next`, `record_attempt`, `theme_counts`, `tactics_status`).
- Create `core/stats.py` — `theme_stats`.
- Create `api/routes/tactics.py`; modify `api/app.py` (router, `tactics_source`).
- Modify `pyproject.toml` — `zstandard>=0.23`.
- Tests: `tests/test_tactics_convert.py`, `tests/test_tactics_rating.py`, `tests/test_tactics_importer.py`, `tests/test_tactics_service.py`, `tests/test_api_tactics.py`, `tests/test_stats.py`, `tests/test_config.py` (append).

Frontend (`frontend/src/`):
- Modify `api/types.ts`, `api/client.ts`, `api/queries.ts`, `lib/format.ts`.
- Modify `train/usePuzzle.ts` (genérico), `train/PuzzleView.tsx` (`Trainable`), `train/SessionStart.tsx` (fonte + temas), `train/TrainPage.tsx` (roteia para a sessão de táticas).
- Create `train/TacticSession.tsx`, `train/TacticResultPanel.tsx`, `train/TacticSummary.tsx`, `train/ThemePicker.tsx`.
- Modify `pages/SettingsPage.tsx`, `pages/DashboardPage.tsx`, `components/JobCard.tsx`; create `components/ThemeBars.tsx`.
- Tests ao lado dos arquivos (`*.test.tsx`), como os existentes.

---

### Task 1: Modelos, configurações e dependência

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/chess_trainer/core/models.py`
- Modify: `backend/chess_trainer/config.py`
- Modify: `backend/chess_trainer/api/schemas.py` (`SettingsOut`, `SettingsIn`)
- Test: `backend/tests/test_models.py` (append), `backend/tests/test_config.py` (append)

**Interfaces:**
- Produces: modelos `LichessPuzzle(id, fen, moves, rating, rating_deviation, popularity, nb_plays, themes, opening_tags)`, `LichessPuzzleTheme(theme, puzzle_id)` (PK composta), `TacticsAttempt(id, puzzle_id, session_id, attempted_at, correct, used_hint, duration_ms, rating_before, rating_after, puzzle_rating)`; `AppSettings.tactics_rating=1200`, `tactics_window=150`, `lichess_min_plays=200`, `lichess_min_popularity=60`.

- [ ] **Step 1: Dependência**

Em `backend/pyproject.toml`, adicionar `"zstandard>=0.23",` à lista `dependencies`. Rodar `cd backend && uv sync` (o `uv.lock` muda; commitar junto).

- [ ] **Step 2: Teste dos modelos (falha)**

Anexar em `backend/tests/test_models.py`:

```python
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, TacticsAttempt


def test_lichess_puzzle_roundtrip(db_session):
    db_session.add(LichessPuzzle(id="00sHx", fen="q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17",
                                 moves="e8d7 a2e6 d7d8 f7f8", rating=1760, rating_deviation=80,
                                 popularity=83, nb_plays=72, themes="mate mateIn2 middlegame short",
                                 opening_tags=""))
    db_session.add(LichessPuzzleTheme(theme="mateIn2", puzzle_id="00sHx"))
    db_session.commit()
    row = db_session.get(LichessPuzzle, "00sHx")
    assert row.rating == 1760 and row.theme_list == ["mate", "mateIn2", "middlegame", "short"]


def test_tactics_attempt_defaults(db_session):
    db_session.add(LichessPuzzle(id="p1", fen="8/8/8/8/8/8/8/K6k w - - 0 1", moves="a1a2", rating=1000,
                                 rating_deviation=50, popularity=90, nb_plays=500, themes="endgame", opening_tags=""))
    a = TacticsAttempt(puzzle_id="p1", correct=True, used_hint=False, duration_ms=1200,
                       rating_before=1200, rating_after=1210, puzzle_rating=1000)
    db_session.add(a)
    db_session.commit()
    assert a.id and a.attempted_at is not None and a.session_id is None
```

Run: `cd backend && uv run pytest tests/test_models.py -q` → FAIL (ImportError).

- [ ] **Step 3: Modelos**

Anexar ao fim de `backend/chess_trainer/core/models.py` (antes de `class Setting` ou depois, tanto faz):

```python
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
```

Run: `cd backend && uv run pytest tests/test_models.py -q` → PASS.

- [ ] **Step 4: Teste das configurações (falha)**

Anexar em `backend/tests/test_config.py`:

```python
def test_tactics_settings_defaults(db_session):
    s = load_settings(db_session)
    assert (s.tactics_rating, s.tactics_window, s.lichess_min_plays, s.lichess_min_popularity) == (1200, 150, 200, 60)
```

(`load_settings` já está importado no arquivo; conferir.) Run → FAIL.

- [ ] **Step 5: Configurações**

Em `config.py`, `AppSettings` ganha ao fim:

```python
    tactics_rating: int = 1200
    tactics_window: int = 150
    lichess_min_plays: int = 200
    lichess_min_popularity: int = 60
```

Em `api/schemas.py`, `SettingsOut` ganha `tactics_rating: int`, `tactics_window: int`, `lichess_min_plays: int`, `lichess_min_popularity: int`; `SettingsIn` ganha os mesmos como `int | None = None`.

Run: `cd backend && uv run pytest -q` → todos passam (172 + 3).

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/chess_trainer/core/models.py backend/chess_trainer/config.py backend/chess_trainer/api/schemas.py backend/tests/test_models.py backend/tests/test_config.py
git commit -m "feat(taticas): modelos do banco do Lichess, tentativas e configurações"
```

---

### Task 2: Temas, conversão em puzzle jogável e Elo

**Files:**
- Create: `backend/chess_trainer/core/tactics/__init__.py` (vazio)
- Create: `backend/chess_trainer/core/tactics/themes.py`
- Create: `backend/chess_trainer/core/tactics/convert.py`
- Create: `backend/chess_trainer/core/tactics/rating.py`
- Test: `backend/tests/test_tactics_convert.py`, `backend/tests/test_tactics_rating.py`

**Interfaces:**
- Produces: `THEME_LABELS: dict[str, str]`, `THEME_PRIORITY: list[str]`, `primary_theme(themes: list[str]) -> str`; `Tactic` dataclass e `to_tactic(row: LichessPuzzle) -> Tactic`; `elo_update(user: int, puzzle: int, success: bool, k: int = 32) -> int`.

- [ ] **Step 1: Testes (falham)**

`backend/tests/test_tactics_convert.py`:

```python
import pytest

from chess_trainer.core.models import LichessPuzzle
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.themes import THEME_LABELS, primary_theme


def row(**kw) -> LichessPuzzle:
    base = dict(id="00sHx", fen="q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17",
                moves="e8d7 a2e6 d7d8 f7f8", rating=1760, rating_deviation=80, popularity=83, nb_plays=72,
                themes="mate mateIn2 middlegame short", opening_tags="")
    base.update(kw)
    return LichessPuzzle(**base)


def test_to_tactic_applies_opponent_move_and_alternates():
    t = to_tactic(row())
    # depois de e8d7 são as brancas que jogam
    assert t.side_to_move == "white"
    assert t.fen_start.split()[1] == "w"
    assert [m["uci"] for m in t.solution["moves"]] == ["a2e6", "d7d8", "f7f8"]
    assert [m["by"] for m in t.solution["moves"]] == ["solver", "engine", "solver"]
    assert all(m["alternatives"] == [] for m in t.solution["moves"])
    assert t.solver_moves == 2
    assert t.end_reason == "mate"
    assert t.theme == "mateIn2" and t.themes == ["mate", "mateIn2", "middlegame", "short"]
    assert t.lichess_url == "https://lichess.org/training/00sHx"
    assert t.rating == 1760 and t.kind == "tactic"


def test_to_tactic_material_gain_when_no_mate():
    # brancas capturam a dama com garfo de cavalo depois do lance preto
    t = to_tactic(row(id="fork1", fen="r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
                      moves="a2a3 f6e4 d2d3 e4c5", themes="fork middlegame short"))
    assert t.end_reason == "material_gain" and t.theme == "fork"


def test_to_tactic_rejects_illegal_move():
    with pytest.raises(ValueError):
        to_tactic(row(moves="e8e1 a2e6"))


def test_primary_theme_prefers_tactical_motif_over_phase():
    assert primary_theme(["middlegame", "short", "fork", "crushing"]) == "fork"
    assert primary_theme(["endgame", "long"]) == "endgame"
    assert primary_theme([]) == "tactic"


def test_every_priority_theme_has_label():
    from chess_trainer.core.tactics.themes import THEME_PRIORITY
    assert all(t in THEME_LABELS for t in THEME_PRIORITY)
```

`backend/tests/test_tactics_rating.py`:

```python
from chess_trainer.core.tactics.rating import elo_update


def test_equal_ratings_win_gives_plus_16():
    assert elo_update(1200, 1200, True) == 1216


def test_equal_ratings_loss_gives_minus_16():
    assert elo_update(1200, 1200, False) == 1184


def test_beating_much_stronger_puzzle_gives_more():
    assert elo_update(1200, 1600, True) > elo_update(1200, 1000, True)


def test_never_below_floor():
    assert elo_update(410, 1500, False) == 400
```

Run: `cd backend && uv run pytest tests/test_tactics_convert.py tests/test_tactics_rating.py -q` → FAIL (ImportError).

- [ ] **Step 2: Temas**

`backend/chess_trainer/core/tactics/themes.py`:

```python
"""Temas do banco do Lichess: tradução e prioridade para escolher o tema principal."""

THEME_LABELS: dict[str, str] = {
    "fork": "garfo", "pin": "cravada", "skewer": "espeto", "discoveredAttack": "ataque descoberto",
    "doubleCheck": "xeque duplo", "hangingPiece": "peça pendurada", "trappedPiece": "peça presa",
    "deflection": "desvio", "attraction": "atração", "clearance": "limpeza", "interference": "interferência",
    "intermezzo": "lance intermediário", "sacrifice": "sacrifício", "xRayAttack": "raio X",
    "capturingDefender": "captura do defensor", "backRankMate": "mate na última fileira",
    "smotheredMate": "mate sufocado", "anastasiaMate": "mate de Anastasia", "arabianMate": "mate árabe",
    "bodenMate": "mate de Boden", "doubleBishopMate": "mate dos dois bispos", "dovetailMate": "mate cauda de andorinha",
    "hookMate": "mate do gancho", "killBoxMate": "mate da caixa", "vukovicMate": "mate de Vukovic",
    "promotion": "promoção", "underPromotion": "subpromoção", "advancedPawn": "peão avançado",
    "exposedKing": "rei exposto", "kingsideAttack": "ataque na ala do rei", "queensideAttack": "ataque na ala da dama",
    "attackingF2F7": "ataque a f2/f7", "quietMove": "lance quieto", "defensiveMove": "lance defensivo",
    "zugzwang": "zugzwang", "enPassant": "en passant", "castling": "roque",
    "mateIn1": "mate em 1", "mateIn2": "mate em 2", "mateIn3": "mate em 3", "mateIn4": "mate em 4", "mateIn5": "mate em 5",
    "mate": "mate", "crushing": "esmagador", "advantage": "vantagem", "equality": "igualdade",
    "opening": "abertura", "middlegame": "meio-jogo", "endgame": "final",
    "pawnEndgame": "final de peões", "rookEndgame": "final de torres", "bishopEndgame": "final de bispos",
    "knightEndgame": "final de cavalos", "queenEndgame": "final de damas", "queenRookEndgame": "final de dama e torre",
    "oneMove": "um lance", "short": "curto", "long": "longo", "veryLong": "muito longo",
    "master": "partida de mestre", "masterVsMaster": "mestre contra mestre", "superGM": "super GM",
    "tactic": "tática",
}

# ordem de preferência para o tema principal: motivos táticos antes de mates
# nomeados, mates antes de fase/duração. Tudo que está aqui tem rótulo.
THEME_PRIORITY: list[str] = [
    "fork", "pin", "skewer", "discoveredAttack", "doubleCheck", "hangingPiece", "trappedPiece",
    "deflection", "attraction", "clearance", "interference", "intermezzo", "sacrifice", "xRayAttack",
    "capturingDefender", "backRankMate", "smotheredMate", "anastasiaMate", "arabianMate", "bodenMate",
    "doubleBishopMate", "dovetailMate", "hookMate", "killBoxMate", "vukovicMate", "promotion", "underPromotion",
    "advancedPawn", "exposedKing", "kingsideAttack", "queensideAttack", "attackingF2F7", "quietMove",
    "defensiveMove", "zugzwang", "enPassant", "castling", "mateIn1", "mateIn2", "mateIn3", "mateIn4", "mateIn5",
    "mate", "pawnEndgame", "rookEndgame", "bishopEndgame", "knightEndgame", "queenEndgame", "queenRookEndgame",
    "opening", "middlegame", "endgame",
]

# temas dos puzzles próprios (core/puzzles/themes.py) com equivalente no Lichess
OWN_THEME_TO_LICHESS: dict[str, str] = {
    "fork": "fork", "pin": "pin", "discovered_attack": "discoveredAttack", "hanging_piece": "hangingPiece",
    "tactic": "tactic",
}

_RANK = {t: i for i, t in enumerate(THEME_PRIORITY)}


def primary_theme(themes: list[str]) -> str:
    ranked = sorted((t for t in themes if t in _RANK), key=_RANK.__getitem__)
    if ranked:
        return ranked[0]
    return themes[0] if themes else "tactic"


def normalize_own_theme(theme: str) -> str:
    """Tema de um puzzle próprio → nome do Lichess (mate_in_N → mateInN)."""
    if theme.startswith("mate_in_"):
        n = theme[8:]
        return f"mateIn{n}" if n.isdigit() and int(n) <= 5 else "mate"
    return OWN_THEME_TO_LICHESS.get(theme, theme)
```

- [ ] **Step 3: Conversão**

`backend/chess_trainer/core/tactics/convert.py`:

```python
from dataclasses import dataclass, field

import chess

from chess_trainer.core.models import LichessPuzzle
from chess_trainer.core.tactics.themes import primary_theme

LICHESS_TRAINING_URL = "https://lichess.org/training/{id}"


@dataclass
class Tactic:
    id: str
    fen_start: str
    side_to_move: str
    solution: dict
    end_reason: str
    theme: str
    themes: list[str]
    rating: int
    solver_moves: int
    lichess_url: str
    kind: str = "tactic"
    category: str = "lichess"
    popularity: int = 0
    nb_plays: int = 0
    opening_tags: list[str] = field(default_factory=list)


def to_tactic(row: LichessPuzzle) -> Tactic:
    """Aplica o lance do adversário e monta a solução no formato dos puzzles próprios.

    Levanta ValueError se algum lance for ilegal (linha corrompida)."""
    board = chess.Board(row.fen)
    ucis = row.moves.split()
    if len(ucis) < 2:
        raise ValueError(f"puzzle {row.id}: menos de dois lances")
    _push(board, ucis[0], row.id)
    fen_start = board.fen()
    side = "white" if board.turn == chess.WHITE else "black"
    moves = []
    for i, uci in enumerate(ucis[1:]):
        _push(board, uci, row.id)
        moves.append({"uci": uci, "by": "solver" if i % 2 == 0 else "engine", "alternatives": []})
    end_reason = "mate" if board.is_checkmate() else "material_gain"
    themes = row.theme_list
    return Tactic(
        id=row.id, fen_start=fen_start, side_to_move=side,
        solution={"moves": moves, "explanation_pv": []}, end_reason=end_reason,
        theme=primary_theme(themes), themes=themes, rating=row.rating,
        solver_moves=sum(1 for m in moves if m["by"] == "solver"),
        lichess_url=LICHESS_TRAINING_URL.format(id=row.id),
        popularity=row.popularity, nb_plays=row.nb_plays,
        opening_tags=row.opening_tags.split() if row.opening_tags else [],
    )


def _push(board: chess.Board, uci: str, puzzle_id: str) -> None:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise ValueError(f"puzzle {puzzle_id}: lance inválido {uci}") from exc
    if move not in board.legal_moves:
        raise ValueError(f"puzzle {puzzle_id}: lance ilegal {uci} em {board.fen()}")
    board.push(move)
```

- [ ] **Step 4: Elo**

`backend/chess_trainer/core/tactics/rating.py`:

```python
RATING_FLOOR = 400
RATING_CEIL = 3200


def elo_update(user: int, puzzle: int, success: bool, k: int = 32) -> int:
    """Elo simplificado: o puzzle é o adversário; acerto sem dica = vitória."""
    expected = 1.0 / (1.0 + 10 ** ((puzzle - user) / 400.0))
    score = 1.0 if success else 0.0
    updated = round(user + k * (score - expected))
    return max(RATING_FLOOR, min(RATING_CEIL, updated))
```

Run: `cd backend && uv run pytest tests/test_tactics_convert.py tests/test_tactics_rating.py -q` → PASS. Se `test_to_tactic_material_gain_when_no_mate` falhar por lance ilegal, corrigir a sequência do teste (a posição é a Italiana após 3...Cf6 com brancas a jogar: `a2a3` é o lance "do adversário", depois `f6e4 d2d3 e4c5` — todos legais).

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/core/tactics backend/tests/test_tactics_convert.py backend/tests/test_tactics_rating.py
git commit -m "feat(taticas): temas traduzidos, conversão de puzzle do Lichess e Elo"
```

---

### Task 3: Importador em streaming e download

**Files:**
- Create: `backend/chess_trainer/core/tactics/importer.py`
- Test: `backend/tests/test_tactics_importer.py`

**Interfaces:**
- Consumes: modelos da Task 1.
- Produces: `ImportFilter(min_plays: int, min_popularity: int, min_rating: int = 400, max_rating: int = 3000)`, `ImportStats(rows_read: int, imported: int, skipped: int, cancelled: bool)`, `parse_rows(lines: Iterable[str]) -> Iterator[dict]`, `import_csv_zst(db: Session, path: Path, flt: ImportFilter, progress: ProgressFn, should_stop=None, batch_size=5000) -> ImportStats`, `download_file(url: str, dest: Path, progress: ProgressFn, should_stop=None, http: httpx.Client | None = None) -> Path`, `write_csv_zst(path: Path, rows: list[dict])` (helper para testes e fixtures).

- [ ] **Step 1: Testes (falham)**

`backend/tests/test_tactics_importer.py`:

```python
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme
from chess_trainer.core.tactics.importer import ImportFilter, download_file, import_csv_zst, write_csv_zst

ROWS = [
    {"PuzzleId": "00sHx", "FEN": "q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17", "Moves": "e8d7 a2e6 d7d8 f7f8",
     "Rating": "1760", "RatingDeviation": "80", "Popularity": "83", "NbPlays": "720", "Themes": "mate mateIn2 middlegame short",
     "GameUrl": "https://lichess.org/yyznGmXs/black#34", "OpeningTags": ""},
    {"PuzzleId": "00sJ9", "FEN": "r3r1k1/p4ppp/2p2n2/1p6/3P1qb1/2NQR3/PPB2PP1/R1B3K1 w - - 5 18", "Moves": "e3g3 e8e1 g1h2 e1c1 a1c1 f4h6 h2g1 h6c1",
     "Rating": "2671", "RatingDeviation": "105", "Popularity": "87", "NbPlays": "325", "Themes": "advantage attraction fork middlegame sacrifice veryLong",
     "GameUrl": "https://lichess.org/gyFeQsOE#35", "OpeningTags": "Kings_Pawn_Game Kings_Pawn_Game_Leonardis_Variation"},
    {"PuzzleId": "unpop", "FEN": "8/8/8/8/8/8/8/K6k w - - 0 1", "Moves": "a1a2 h1h2", "Rating": "1500", "RatingDeviation": "80",
     "Popularity": "10", "NbPlays": "900", "Themes": "endgame", "GameUrl": "", "OpeningTags": ""},
    {"PuzzleId": "rare", "FEN": "8/8/8/8/8/8/8/K6k w - - 0 1", "Moves": "a1a2 h1h2", "Rating": "1500", "RatingDeviation": "80",
     "Popularity": "95", "NbPlays": "12", "Themes": "endgame", "GameUrl": "", "OpeningTags": ""},
    {"PuzzleId": "tooHi", "FEN": "8/8/8/8/8/8/8/K6k w - - 0 1", "Moves": "a1a2 h1h2", "Rating": "3100", "RatingDeviation": "80",
     "Popularity": "95", "NbPlays": "900", "Themes": "endgame", "GameUrl": "", "OpeningTags": ""},
]
FLT = ImportFilter(min_plays=200, min_popularity=60)


@pytest.fixture
def csv_zst(tmp_path: Path) -> Path:
    path = tmp_path / "puzzles.csv.zst"
    write_csv_zst(path, ROWS)
    return path


def test_import_filters_and_indexes_themes(db_session, csv_zst):
    calls = []
    stats = import_csv_zst(db_session, csv_zst, FLT, lambda *a: calls.append(a), batch_size=2)
    assert (stats.rows_read, stats.imported, stats.skipped, stats.cancelled) == (5, 2, 3, False)
    assert db_session.scalar(select(func.count(LichessPuzzle.id))) == 2
    themes = set(db_session.scalars(select(LichessPuzzleTheme.theme).where(LichessPuzzleTheme.puzzle_id == "00sJ9")))
    assert themes == {"advantage", "attraction", "fork", "middlegame", "sacrifice", "veryLong"}
    assert db_session.get(LichessPuzzle, "00sJ9").opening_tags == "Kings_Pawn_Game Kings_Pawn_Game_Leonardis_Variation"
    assert calls and calls[-1][0] == "import" and calls[-1][1] == 5


def test_import_is_idempotent(db_session, csv_zst):
    import_csv_zst(db_session, csv_zst, FLT, lambda *a: None)
    again = import_csv_zst(db_session, csv_zst, FLT, lambda *a: None)
    assert again.imported == 0 and db_session.scalar(select(func.count(LichessPuzzle.id))) == 2
    assert db_session.scalar(select(func.count()).select_from(LichessPuzzleTheme)) == 10


def test_import_stops_between_batches(db_session, csv_zst):
    stats = import_csv_zst(db_session, csv_zst, FLT, lambda *a: None, should_stop=lambda: True, batch_size=1)
    assert stats.cancelled is True and stats.rows_read <= 2


def test_download_streams_and_reports_progress(tmp_path: Path):
    payload = b"x" * 10_000
    seen = []

    def handler(request: httpx.Request):
        return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

    dest = tmp_path / "db.csv.zst"
    out = download_file("https://example.test/db.zst", dest, lambda *a: seen.append(a),
                        http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert out == dest and dest.read_bytes() == payload and not (tmp_path / "db.csv.zst.part").exists()
    assert seen[-1][0] == "download" and seen[-1][1] == len(payload) == seen[-1][2]


def test_download_skips_when_size_matches(tmp_path: Path):
    dest = tmp_path / "db.csv.zst"
    dest.write_bytes(b"abc")

    def handler(request: httpx.Request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": "3"})
        raise AssertionError("não deveria baixar de novo")

    download_file("https://example.test/db.zst", dest, lambda *a: None,
                  http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert dest.read_bytes() == b"abc"
```

Run: `cd backend && uv run pytest tests/test_tactics_importer.py -q` → FAIL.

- [ ] **Step 2: Implementação**

`backend/chess_trainer/core/tactics/importer.py`:

```python
"""Importa o banco de puzzles do Lichess (CSV comprimido com zstd) em streaming."""
import csv
import io
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import zstandard
from sqlalchemy import insert
from sqlalchemy.orm import Session

from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme

LICHESS_PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
COLUMNS = ["PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation", "Popularity", "NbPlays", "Themes", "GameUrl", "OpeningTags"]
ProgressFn = Callable[[str, int, int, str], None]
StopFn = Callable[[], bool]


@dataclass(frozen=True)
class ImportFilter:
    min_plays: int
    min_popularity: int
    min_rating: int = 400
    max_rating: int = 3000

    def accepts(self, row: dict) -> bool:
        return (row["nb_plays"] >= self.min_plays and row["popularity"] >= self.min_popularity
                and self.min_rating <= row["rating"] <= self.max_rating)


@dataclass
class ImportStats:
    rows_read: int = 0
    imported: int = 0
    skipped: int = 0
    cancelled: bool = False


def parse_rows(lines: Iterable[str]) -> Iterator[dict]:
    """Linhas de texto do CSV → dicts com os tipos certos. A primeira linha é o cabeçalho."""
    reader = csv.DictReader(lines)
    for raw in reader:
        try:
            yield {
                "id": raw["PuzzleId"], "fen": raw["FEN"], "moves": raw["Moves"],
                "rating": int(raw["Rating"]), "rating_deviation": int(raw["RatingDeviation"]),
                "popularity": int(raw["Popularity"]), "nb_plays": int(raw["NbPlays"]),
                "themes": raw["Themes"] or "", "opening_tags": raw.get("OpeningTags") or "",
            }
        except (KeyError, ValueError, TypeError):
            continue  # linha corrompida: pula sem derrubar a importação


def _open_zst_text(path: Path) -> io.TextIOWrapper:
    fh = open(path, "rb")
    reader = zstandard.ZstdDecompressor().stream_reader(fh)
    return io.TextIOWrapper(reader, encoding="utf-8", newline="")


def import_csv_zst(db: Session, path: Path, flt: ImportFilter, progress: ProgressFn,
                   should_stop: StopFn | None = None, batch_size: int = 5000) -> ImportStats:
    stats = ImportStats()
    batch: list[dict] = []
    themes: list[dict] = []

    def flush() -> None:
        if not batch:
            return
        # INSERT OR IGNORE: rodar de novo completa o que faltou sem duplicar
        db.execute(insert(LichessPuzzle).prefix_with("OR IGNORE"), batch)
        db.execute(insert(LichessPuzzleTheme).prefix_with("OR IGNORE"), themes)
        db.commit()
        batch.clear()
        themes.clear()

    with _open_zst_text(path) as text:
        for row in parse_rows(text):
            stats.rows_read += 1
            if flt.accepts(row):
                batch.append(row)
                themes.extend({"theme": t, "puzzle_id": row["id"]} for t in row["themes"].split())
            else:
                stats.skipped += 1
            if len(batch) >= batch_size:
                before = db.scalar(_count()) or 0
                flush()
                stats.imported += (db.scalar(_count()) or 0) - before
                progress("import", stats.rows_read, 0, f"{stats.rows_read:,} linhas lidas · {stats.imported:,} táticas novas".replace(",", "."))
                if should_stop is not None and should_stop():
                    stats.cancelled = True
                    return stats
    before = db.scalar(_count()) or 0
    flush()
    stats.imported += (db.scalar(_count()) or 0) - before
    progress("import", stats.rows_read, 0, f"{stats.rows_read:,} linhas lidas · {stats.imported:,} táticas novas".replace(",", "."))
    return stats


def _count():
    from sqlalchemy import func, select
    return select(func.count(LichessPuzzle.id))


def download_file(url: str, dest: Path, progress: ProgressFn, should_stop: StopFn | None = None,
                  http: httpx.Client | None = None) -> Path:
    """Baixa `url` para `dest` em streaming (via `.part`), pulando se o arquivo já tem o tamanho remoto."""
    client = http or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=120.0))
    try:
        head = client.head(url, follow_redirects=True)
        remote_size = int(head.headers.get("content-length", "0") or 0)
        if dest.exists() and remote_size and dest.stat().st_size == remote_size:
            progress("download", remote_size, remote_size, "arquivo já baixado")
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        done = 0
        with client.stream("GET", url, follow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", "0") or 0) or remote_size
            with open(part, "wb") as out:
                for chunk in resp.iter_bytes(1 << 20):
                    out.write(chunk)
                    done += len(chunk)
                    progress("download", done, total, f"{done / 2**20:.0f} MB baixados")
                    if should_stop is not None and should_stop():
                        raise RuntimeError("download cancelado")
        part.replace(dest)
        return dest
    finally:
        if http is None:
            client.close()


def write_csv_zst(path: Path, rows: list[dict]) -> None:
    """Escreve um CSV no formato do Lichess comprimido com zstd (fixtures e testes)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zstandard.ZstdCompressor().compress(buf.getvalue().encode("utf-8")))
```

Observação: um download cancelado deixa o `.part` e o job termina em erro "download cancelado" — aceitável; o próximo "Baixar e importar" recomeça do zero.

Run: `cd backend && uv run pytest tests/test_tactics_importer.py -q` → PASS. Rodar a suíte inteira.

- [ ] **Step 3: Commit**

```bash
git add backend/chess_trainer/core/tactics/importer.py backend/tests/test_tactics_importer.py
git commit -m "feat(taticas): importador em streaming do CSV do Lichess e download com progresso"
```

---

### Task 4: Seleção, tentativas, estatísticas e rotas da API

**Files:**
- Create: `backend/chess_trainer/core/tactics/service.py`
- Create: `backend/chess_trainer/core/stats.py`
- Create: `backend/chess_trainer/api/routes/tactics.py`
- Modify: `backend/chess_trainer/api/schemas.py`, `backend/chess_trainer/api/app.py`
- Test: `backend/tests/test_tactics_service.py`, `backend/tests/test_stats.py`, `backend/tests/test_api_tactics.py`

**Interfaces:**
- Consumes: Task 2 (`to_tactic`, `elo_update`, `primary_theme`, `normalize_own_theme`, `THEME_LABELS`), Task 3 (`import_csv_zst`, `download_file`, `ImportFilter`, `LICHESS_PUZZLE_URL`).
- Produces: `pick_next(db, settings, now, themes: list[str] = (), exclude: list[str] = ()) -> LichessPuzzle | None`; `record_attempt(db, puzzle_id, *, correct, used_hint, duration_ms, session_id, now, settings) -> TacticsAttempt` (atualiza `tactics_rating` via `set_setting`); `theme_counts(db) -> list[tuple[str, int]]`; `tactics_status(db, now) -> dict`; `theme_stats(db, since: datetime) -> list[dict(theme, label, attempts, correct, accuracy, own, lichess)]`.
- Rotas: `GET /api/tactics/status`, `POST /api/tactics/import` (202/409), `GET /api/tactics/next?themes=&exclude=`, `POST /api/tactics/attempts`, `GET /api/tactics/themes`, `GET /api/stats/themes?days=30`.
- `create_app(..., tactics_source: str | Path | None = None)`: caminho local (sem download) ou URL; padrão `LICHESS_PUZZLE_URL` com destino `BACKEND_DIR / "data" / "lichess_db_puzzle.csv.zst"`.

- [ ] **Step 1: Testes do serviço (falham)**

`backend/tests/test_tactics_service.py`:

```python
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
```

`backend/tests/test_stats.py`:

```python
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
```

(Conferir a assinatura de `make_puzzle` em `tests/factories.py` e ajustar os kwargs; se `Review` exigir campos extras, preencher com os padrões do modelo.)

- [ ] **Step 2: Serviço**

`backend/chess_trainer/core/tactics/service.py`:

```python
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, get_setting, set_setting
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, TacticsAttempt
from chess_trainer.core.srs.queue import local_day_start
from chess_trainer.core.tactics.rating import elo_update

WIDEN_STEP = 100
MAX_WINDOW = 1200
FAILED_COOLDOWN = timedelta(days=1)
SAMPLE = 50


def _candidates(db: Session, lo: int, hi: int, themes: Sequence[str], exclude: Sequence[str], now: datetime):
    q = select(LichessPuzzle.id).where(LichessPuzzle.rating.between(lo, hi))
    if themes:
        q = q.where(LichessPuzzle.id.in_(select(LichessPuzzleTheme.puzzle_id).where(LichessPuzzleTheme.theme.in_(list(themes)))))
    if exclude:
        q = q.where(LichessPuzzle.id.not_in(list(exclude)))
    solved = select(TacticsAttempt.puzzle_id).where(TacticsAttempt.correct.is_(True))
    recent_fail = select(TacticsAttempt.puzzle_id).where(TacticsAttempt.attempted_at > now - FAILED_COOLDOWN)
    q = q.where(LichessPuzzle.id.not_in(solved)).where(LichessPuzzle.id.not_in(recent_fail))
    return q


def pick_next(db: Session, settings: AppSettings, now: datetime, themes: Sequence[str] = (),
              exclude: Sequence[str] = ()) -> LichessPuzzle | None:
    """Sorteia uma tática na janela de rating; errados antigos têm prioridade; alarga a janela se vazio."""
    window = settings.tactics_window
    while window <= MAX_WINDOW:
        lo, hi = settings.tactics_rating - window, settings.tactics_rating + window
        base = _candidates(db, lo, hi, themes, exclude, now)
        failed = base.where(exists().where(TacticsAttempt.puzzle_id == LichessPuzzle.id))
        ids = db.scalars(failed.order_by(func.random()).limit(SAMPLE)).all()
        if not ids:
            ids = db.scalars(base.order_by(func.random()).limit(SAMPLE)).all()
        if ids:
            return db.get(LichessPuzzle, ids[0])
        if db.scalar(select(func.count(LichessPuzzle.id))) == 0:
            return None
        window += WIDEN_STEP
    return None


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
    db.commit()
    set_setting(db, "tactics_rating", after)
    return attempt


def theme_counts(db: Session) -> list[tuple[str, int]]:
    rows = db.execute(select(LichessPuzzleTheme.theme, func.count()).group_by(LichessPuzzleTheme.theme)
                      .order_by(func.count().desc())).all()
    return [(t, int(n)) for t, n in rows]


def tactics_status(db: Session, now: datetime) -> dict:
    count = int(db.scalar(select(func.count(LichessPuzzle.id))) or 0)
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
```

`backend/chess_trainer/core/stats.py`:

```python
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
```

Run: `cd backend && uv run pytest tests/test_tactics_service.py tests/test_stats.py -q` → PASS.

- [ ] **Step 3: Schemas e rotas**

Em `api/schemas.py`, anexar:

```python
class TacticOut(BaseModel):
    id: str
    kind: str = "tactic"
    fen_start: str
    side_to_move: str
    solution: dict
    end_reason: str
    theme: str
    themes: list[str]
    category: str = "lichess"
    rating: int
    solver_moves: int
    lichess_url: str
    popularity: int
    nb_plays: int
    opening_tags: list[str] = []


class AttemptIn(BaseModel):
    puzzle_id: str
    session_id: str | None = None
    correct: bool
    used_hint: bool = False
    duration_ms: int = 0


class AttemptOut(BaseModel):
    id: str
    puzzle_id: str
    correct: bool
    used_hint: bool
    rating_before: int
    rating_after: int
    delta: int
    puzzle_rating: int


class TacticsStatusOut(BaseModel):
    imported: bool
    count: int
    imported_at: str | None
    source_rows: int | None
    rating: int
    window: int
    attempts_total: int
    attempts_today: int
    attempts_30d: int
    correct_30d: int


class ThemeCountOut(BaseModel):
    theme: str
    label: str
    count: int


class ThemeStatOut(BaseModel):
    theme: str
    label: str
    attempts: int
    correct: int
    accuracy: float
    own: int
    lichess: int
```

`backend/chess_trainer/api/routes/tactics.py`:

```python
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import AttemptIn, AttemptOut, TacticOut, TacticsStatusOut, ThemeCountOut, ThemeStatOut
from chess_trainer.config import load_settings, set_setting
from chess_trainer.core.models import TrainingSession, utcnow
from chess_trainer.core.stats import theme_stats
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.importer import ImportFilter, download_file, import_csv_zst
from chess_trainer.core.tactics.service import pick_next, record_attempt, tactics_status, theme_counts
from chess_trainer.core.tactics.themes import THEME_LABELS

router = APIRouter(prefix="/api")


def _csv(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


@router.get("/tactics/status", response_model=TacticsStatusOut)
def get_status(db: Session = Depends(get_db)):
    return tactics_status(db, utcnow())


@router.post("/tactics/import", status_code=202)
def post_import(request: Request):
    app = request.app
    source = app.state.tactics_source
    dest = app.state.tactics_dest

    def job(progress):
        session = app.state.session_factory()
        try:
            s = load_settings(session)
            path = Path(source)
            if not path.is_file():
                path = download_file(str(source), Path(dest), progress, should_stop=app.state.jobs.should_stop)
            flt = ImportFilter(min_plays=s.lichess_min_plays, min_popularity=s.lichess_min_popularity)
            stats = import_csv_zst(session, path, flt, progress, should_stop=app.state.jobs.should_stop)
            if not stats.cancelled:
                set_setting(session, "lichess_imported_at", utcnow().isoformat())
                set_setting(session, "lichess_source_rows", stats.rows_read)
            progress("import", stats.rows_read, stats.rows_read,
                     f"{stats.imported} táticas novas de {stats.rows_read} linhas" + (" (cancelado)" if stats.cancelled else ""))
        finally:
            session.close()

    if not app.state.jobs.submit("import_lichess", job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": "import_lichess"}


@router.get("/tactics/next", response_model=TacticOut)
def get_next(themes: str | None = None, exclude: str | None = None, db: Session = Depends(get_db)):
    status = tactics_status(db, utcnow())
    if not status["imported"]:
        raise HTTPException(404, "banco de táticas não importado; baixe em Configurações")
    settings = load_settings(db)
    row = pick_next(db, settings, utcnow(), themes=_csv(themes), exclude=_csv(exclude))
    if row is None:
        raise HTTPException(404, "nenhuma tática disponível com esses filtros")
    try:
        return asdict(to_tactic(row))
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/tactics/attempts", response_model=AttemptOut, status_code=201)
def post_attempt(body: AttemptIn, db: Session = Depends(get_db)):
    if body.session_id is not None and db.get(TrainingSession, body.session_id) is None:
        raise HTTPException(404, "sessão não encontrada")
    try:
        a = record_attempt(db, body.puzzle_id, correct=body.correct, used_hint=body.used_hint,
                           duration_ms=body.duration_ms, session_id=body.session_id, now=utcnow(), settings=load_settings(db))
    except KeyError:
        raise HTTPException(404, "tática não encontrada")
    return AttemptOut(id=a.id, puzzle_id=a.puzzle_id, correct=a.correct, used_hint=a.used_hint,
                      rating_before=a.rating_before, rating_after=a.rating_after,
                      delta=a.rating_after - a.rating_before, puzzle_rating=a.puzzle_rating)


@router.get("/tactics/themes", response_model=list[ThemeCountOut])
def get_themes(db: Session = Depends(get_db)):
    return [ThemeCountOut(theme=t, label=THEME_LABELS.get(t, t), count=n) for t, n in theme_counts(db)]


@router.get("/stats/themes", response_model=list[ThemeStatOut])
def get_theme_stats(days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)):
    return theme_stats(db, since=utcnow() - timedelta(days=days))
```

Em `api/app.py`: importar `tactics` no `from chess_trainer.api.routes import ...`; `create_app` ganha o parâmetro `tactics_source: str | Path | None = None`; após `app.state.analyzer = ...`:

```python
    from chess_trainer.core.tactics.importer import LICHESS_PUZZLE_URL
    app.state.tactics_source = tactics_source or os.environ.get("CHESS_TRAINER_LICHESS_SOURCE", LICHESS_PUZZLE_URL)
    app.state.tactics_dest = BACKEND_DIR / "data" / "lichess_db_puzzle.csv.zst"
```

e `app.include_router(tactics.router)` junto dos outros. (Mover o import para o topo do arquivo.)

- [ ] **Step 4: Testes da API**

`backend/tests/test_api_tactics.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.tactics.importer import write_csv_zst
from tests.fakes import FakeEngine, first_legal_default
from tests.test_tactics_importer import ROWS


@pytest.fixture
def client(tmp_path: Path):
    src = tmp_path / "puzzles.csv.zst"
    write_csv_zst(src, ROWS)
    app = create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)), tactics_source=src)
    with TestClient(app) as c:
        yield c


def run_import(client):
    assert client.post("/api/tactics/import").status_code == 202
    client.app.state.jobs.wait()
    job = client.get("/api/status").json()["job"]
    assert job["state"] == "idle", job


def test_next_404_before_import(client):
    r = client.get("/api/tactics/next")
    assert r.status_code == 404 and "não importado" in r.json()["detail"]
    assert client.get("/api/tactics/status").json()["imported"] is False


def test_import_then_train_flow(client):
    run_import(client)
    st = client.get("/api/tactics/status").json()
    assert st["imported"] and st["count"] == 2 and st["imported_at"] and st["source_rows"] == 5
    themes = client.get("/api/tactics/themes").json()
    assert {t["theme"] for t in themes} >= {"fork", "mateIn2"} and next(t for t in themes if t["theme"] == "fork")["label"] == "garfo"
    r = client.put("/api/settings", json={"tactics_rating": 1760, "tactics_window": 50})
    assert r.status_code == 200 and r.json()["tactics_rating"] == 1760
    t = client.get("/api/tactics/next").json()
    assert t["id"] == "00sHx" and t["kind"] == "tactic" and t["solution"]["moves"][0]["by"] == "solver"
    assert t["lichess_url"].endswith("/training/00sHx") and t["end_reason"] == "mate"
    a = client.post("/api/tactics/attempts", json={"puzzle_id": t["id"], "correct": True, "duration_ms": 5000}).json()
    assert a["rating_before"] == 1760 and a["delta"] == 16 and a["rating_after"] == 1776
    assert client.get("/api/settings").json()["tactics_rating"] == 1776
    # resolvido não volta; com exclude do outro, nada sobra
    r = client.get("/api/tactics/next", params={"exclude": "00sJ9"})
    assert r.status_code == 404
    stats = client.get("/api/stats/themes").json()
    assert stats[0]["theme"] == "mateIn2" and stats[0]["attempts"] == 1 and stats[0]["lichess"] == 1
    assert client.get("/api/tactics/status").json()["attempts_today"] == 1


def test_attempt_unknown_puzzle_404(client):
    run_import(client)
    assert client.post("/api/tactics/attempts", json={"puzzle_id": "nope", "correct": False}).status_code == 404


def test_import_busy_409(client):
    import threading
    gate = threading.Event()
    client.app.state.jobs.submit("import", lambda progress: gate.wait(5))
    try:
        assert client.post("/api/tactics/import").status_code == 409
    finally:
        gate.set()
        client.app.state.jobs.wait()
```

Run: `cd backend && uv run pytest -q` → tudo verde.

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/core/tactics/service.py backend/chess_trainer/core/stats.py backend/chess_trainer/api/routes/tactics.py backend/chess_trainer/api/schemas.py backend/chess_trainer/api/app.py backend/tests/test_tactics_service.py backend/tests/test_stats.py backend/tests/test_api_tactics.py
git commit -m "feat(taticas): seleção por rating e tema, tentativas com Elo, estatísticas e rotas"
```

---

### Task 5: Frontend — tipos, cliente, `usePuzzle` genérico e `PuzzleView` para `Trainable`

**Files:**
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/lib/format.ts`
- Modify: `frontend/src/train/usePuzzle.ts`, `frontend/src/train/PuzzleView.tsx`
- Test: `frontend/src/train/usePuzzle.test.ts(x)` (existente: ajustar tipos), `frontend/src/train/PuzzleView.test.tsx` (criar ou anexar)

**Interfaces:**
- Produces (types.ts):

```ts
export interface TacticOut {
  id: string; kind: "tactic"; fen_start: string; side_to_move: Color; solution: Solution;
  end_reason: "mate" | "material_gain"; theme: string; themes: string[]; category: "lichess";
  rating: number; solver_moves: number; lichess_url: string; popularity: number; nb_plays: number; opening_tags: string[];
}
export type Trainable = PuzzleOut | TacticOut;
export interface AttemptIn { puzzle_id: string; session_id?: string | null; correct: boolean; used_hint?: boolean; duration_ms?: number; }
export interface AttemptOut { id: string; puzzle_id: string; correct: boolean; used_hint: boolean; rating_before: number; rating_after: number; delta: number; puzzle_rating: number; }
export interface TacticsStatus { imported: boolean; count: number; imported_at: string | null; source_rows: number | null; rating: number; window: number; attempts_total: number; attempts_today: number; attempts_30d: number; correct_30d: number; }
export interface ThemeCount { theme: string; label: string; count: number; }
export interface ThemeStat { theme: string; label: string; attempts: number; correct: number; accuracy: number; own: number; lichess: number; }
```

  `Settings` ganha `tactics_rating`, `tactics_window`, `lichess_min_plays`, `lichess_min_popularity` (number). `JobStatus.job` continua string.
- client.ts: `tacticsStatus()`, `importTactics()` (POST `/tactics/import`), `nextTactic(p: {themes?: string[]; exclude?: string[]})` (query `themes=a,b&exclude=x,y`), `attempt(body: AttemptIn)`, `tacticThemes()`, `themeStats(days = 30)`.
- queries.ts: `useTacticsStatus()`, `useTacticThemes()`, `useThemeStats(days)`; `useStartJob` aceita `kind: "import_lichess"`; `useJobWatcher` invalida também `["tactics"]` e `["stats"]`; keys `tacticsStatus: ["tactics","status"]`, `tacticThemes: ["tactics","themes"]`, `themeStats: (d) => ["stats","themes",d]`.
- `usePuzzle<R = ReviewOut>(puzzle: Pick<Trainable, "id" | "fen_start" | "solution">, opts: UsePuzzleOptions<R>)` com `submit: (body: ReviewIn) => Promise<R>` e `state.review?: R`.
- `PuzzleView({ puzzle: Trainable, ctl, clockLabel, orderInfo })`: cabeçalho para tática mostra `"{Brancas|Pretas} jogam · tática"`, tags `themeLabel(theme)` + `rating {n}`, linha `"{solver_moves} lance(s) seu(s)"`; cabeçalho dos próprios não muda.
- `themeLabel` passa a conhecer os temas do Lichess (mesmo mapa da Task 2, em camelCase) — copiar `THEME_LABELS` para `lib/format.ts` como `LICHESS_THEMES`.

- [ ] **Step 1: Tipos, cliente, queries, format** — implementar as interfaces acima. Em `useStartJob`, `mutationFn`: `p.kind === "import_lichess" ? api.importTactics() : ...`.

- [ ] **Step 2: `usePuzzle` genérico** — trocar `PuzzleOut` por `Pick<Trainable, "id" | "fen_start" | "solution">`, parametrizar `R` em `UsePuzzleOptions<R>`, `PuzzleState<R>`, `usePuzzle<R = ReviewOut>`. Nenhuma mudança de comportamento; testes existentes devem continuar passando (`npm test -- --run`).

- [ ] **Step 3: Teste do `PuzzleView` com tática (falha)** — em `frontend/src/train/PuzzleView.test.tsx` (criar se não existir; usar o padrão dos outros testes de componente, com `MemoryRouter` se o componente usar `Link`):

```tsx
const tactic: TacticOut = {
  id: "00sHx", kind: "tactic", fen_start: "q5nr/1ppknQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 w - - 1 18", side_to_move: "white",
  solution: { moves: [{ uci: "a2e6", by: "solver", alternatives: [] }, { uci: "d7d8", by: "engine", alternatives: [] }, { uci: "f7f8", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "mate", theme: "mateIn2", themes: ["mate", "mateIn2"], category: "lichess", rating: 1760, solver_moves: 2,
  lichess_url: "https://lichess.org/training/00sHx", popularity: 83, nb_plays: 720, opening_tags: [],
};

it("mostra cabeçalho de tática com rating e tema traduzido", () => {
  function Host() { const ctl = usePuzzle(tactic, { sessionId: null, submit: async () => ({}) as never }); return <PuzzleView puzzle={tactic} ctl={ctl} />; }
  render(<MemoryRouter><Host /></MemoryRouter>);
  expect(screen.getByText(/Brancas jogam · tática/)).toBeInTheDocument();
  expect(screen.getByText("mate em 2")).toBeInTheDocument();
  expect(screen.getByText(/rating 1760/)).toBeInTheDocument();
});
```

- [ ] **Step 4: `PuzzleView`** — aceitar `Trainable`; `const tactic = puzzle.kind === "tactic"`; ramificar só o bloco de cabeçalho. Os campos `game/ply/srs` só são lidos no ramo dos próprios (TypeScript estreita pelo `kind`).

Run: `cd frontend && npm test -- --run && npm run build` → verde.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(taticas): tipos e cliente da API de táticas; usePuzzle e PuzzleView aceitam táticas"
```

---

### Task 6: Frontend — sessão de táticas na tela Treinar

**Files:**
- Create: `frontend/src/train/ThemePicker.tsx`, `frontend/src/train/TacticSession.tsx`, `frontend/src/train/TacticResultPanel.tsx`, `frontend/src/train/TacticSummary.tsx`
- Modify: `frontend/src/train/SessionStart.tsx`, `frontend/src/train/TrainPage.tsx`
- Test: `frontend/src/train/TacticSession.test.tsx`, `frontend/src/train/SessionStart.test.tsx` (anexar se existir)

**Interfaces:**
- Consumes: Task 5 (`api.nextTactic`, `api.attempt`, `useTacticThemes`, `useTacticsStatus`, `usePuzzle<AttemptOut>`, `PuzzleView`).
- Produces: `SessionConfig` ganha `source: "own" | "tactics"` e `themes: string[]`; `SessionStart` mostra dois botões-rádio de fonte ("Meus erros" / "Táticas do Lichess"); com "tactics", esconde os selects de tipo/cor/categoria e mostra `ThemePicker` (chips dos 20 temas mais frequentes via `useTacticThemes`, traduzidos, multi-seleção, persistido em `storage` `train.themes`), e um aviso com link para `/config` quando `useTacticsStatus().data?.imported === false` (botão Começar desabilitado nesse caso). Persistir `train.source`.
- `TacticSession({ config, onFinish })`: cria `TrainingSession` (`api.createSession({ planned_minutes, filters: { source: "tactics", themes } })`), pede `api.nextTactic({ themes, exclude: seenIds })`, renderiza `<TacticPuzzle key={tactic.id}>` (usa `usePuzzle<AttemptOut>` com `submit: api.attempt`), e ao terminar cada tática acumula `TacticDone { tactic: TacticOut; attempt: AttemptOut }`. Cabeçalho `orderInfo`: `"{n}ª tática · rating {ratingAtual}"`. Relógio e modal "Tempo esgotado" iguais à sessão atual (copiar o padrão de `Session` em `TrainPage.tsx`, incluindo o `startP` ref para StrictMode). `404` do `nextTactic` encerra com o motivo do `detail`; botão "Encerrar sessão" sempre visível (fila é infinita).
- `TacticResultPanel({ tactic, attempt, error, onRetry, onNext, nextDisabled, clockLabel })`: `LineViewer` da solução a partir de `fen_start` (`startPly` = 1 + ply da FEN: `(fullmove-1)*2 + (turn==="b"?1:0)`, abrir em `initialPos = moves.length`), mensagem "Resolvido sem erro." / "Concluído, mas contou como erro.", linha `"Rating {before} → {after} ({+delta})"`, tags dos temas traduzidos + `rating {puzzle_rating}`, links "ver no Lichess" (`lichess_url`, nova aba) e "Explorar" (`/analise?fen=...&orientation=...&back=/treinar`, nova aba), botão Próximo.
- `TacticSummary({ done, elapsedLabel, reason, ratingStart, ratingEnd, onNew })`: total, sem erro, tempo, `"Rating {start} → {end}"`, lista dos errados com link do Lichess.
- `TrainPage`: `config.source === "tactics" ? <TacticSession …> : <Session …>`; o resumo escolhe `TacticSummary` quando a sessão foi de táticas.

- [ ] **Step 1: Testes (falham)** — `TacticSession.test.tsx` com `vi.spyOn(api, ...)`: (a) cria sessão e busca a primeira tática com os temas; (b) após `ctl` resolver (chamar `api.attempt` mockado devolvendo `delta: 16`), o painel mostra "Rating 1200 → 1216 (+16)" e o link do Lichess; (c) clicar Próximo pede a próxima com `exclude` contendo o id anterior; (d) `404` encerra com o `detail` visível. Para resolver a tática no teste, use `ctl` via um helper `act(() => ctl.play(...))` como fazem os testes existentes de `usePuzzle` (ler `usePuzzle.test` para a API real: `onMove`/`play`, promoção etc.). Em `SessionStart.test.tsx`: escolher "Táticas do Lichess" mostra os chips e `onStart` recebe `{ source: "tactics", themes: ["fork"] }` ao clicar em "garfo" e Começar.

- [ ] **Step 2: Implementar** os componentes acima. Estilo: reutilizar classes `card`, `row`, `tag`, `msg ok|bad`, `muted`, `primary`. Chips: `<button className={selected ? "tag selected" : "tag"}>` com `aria-pressed`; adicionar em `styles/base.css` a regra `.tag.selected { background: var(--accent); color: var(--bg); }` (usar os tokens existentes em `styles/tokens.css`; conferir os nomes).

- [ ] **Step 3: Verificar** `npm test -- --run`, `npm run build`, `npx tsc --noEmit` (se o projeto tiver script `typecheck`, usar).

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(taticas): sessão de táticas do Lichess na tela Treinar com filtro de temas e rating"
```

---

### Task 7: Frontend — Configurações, Painel, cartão de tarefas e docs

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`, `frontend/src/pages/DashboardPage.tsx`, `frontend/src/components/JobCard.tsx`
- Create: `frontend/src/components/ThemeBars.tsx`
- Modify: `README.md`, `backend/README.md`
- Test: `frontend/src/pages/SettingsPage.test.tsx` (anexar), `frontend/src/pages/DashboardPage.test.tsx` (anexar/criar), `frontend/src/components/ThemeBars.test.tsx`

**Interfaces:**
- Consumes: Task 5 (`useTacticsStatus`, `useThemeStats`, `useStartJob({kind:"import_lichess"})`, `Settings` novos campos).
- `JobCard`: `JOB_LABEL.import_lichess = "Importação das táticas do Lichess"`, `JOB_RUNNING_HINT.import_lichess = "baixa o banco (~300 MB) e importa as táticas filtradas; pode levar alguns minutos"`; quando `job.total === 0`, mostrar só `job.message` e `<progress>` indeterminado (sem `value`); o texto do botão cancelar vira "Cancelar (após o lote atual)" quando `job.job === "import_lichess"`.
- `SettingsPage`: seção "Banco de táticas (Lichess)" com estado (`"não importado"` ou `"{count} táticas · importado em {formatDate(imported_at)}"`), botão "Baixar e importar" (desabilitado com job rodando; texto do hint: "Download de ~300 MB de database.lichess.org; o arquivo fica em backend/data/"), campos numéricos `tactics_rating` ("Rating inicial de táticas"), `tactics_window` ("Janela de rating (±)"), `lichess_min_plays` ("Mínimo de partidas jogadas"), `lichess_min_popularity` ("Popularidade mínima (−100 a 100)") salvos junto com o resto do formulário; `validate` rejeita `tactics_window < 50`, `tactics_rating` fora de 400–3200, popularidade fora de −100..100, min_plays < 0.
- `DashboardPage`: quando `useTacticsStatus().data?.imported`, cartão "Táticas" com `StatCard`s: rating, tentativas hoje, acerto 30 d (`correct_30d/attempts_30d` em %, "—" sem tentativas) e botão "Treinar táticas" (navega para `/treinar?source=tactics`; `TrainPage`/`SessionStart` lêem o parâmetro para pré-selecionar a fonte — adicionar esse suporte em `SessionStart` via `useSearchParams`). Cartão "Por tema (30 dias)" com `<ThemeBars rows={themeStats} />` quando há linhas; abaixo, "Tema mais fraco: {label} ({acc}%)" para o tema com ≥ 3 tentativas e menor acerto.
- `ThemeBars({ rows: ThemeStat[] })`: lista até 10 linhas, cada uma `label`, barra proporcional a `accuracy` (div com width em %), texto `"{correct}/{attempts}"`; `role="list"`.

- [ ] **Step 1: Testes (falham)** — `ThemeBars.test.tsx`: renderiza rótulos e contagens; `SettingsPage.test.tsx`: com `tacticsStatus` mockado `imported:false`, mostra "não importado" e o botão "Baixar e importar" dispara `api.importTactics`; `DashboardPage.test.tsx`: com `imported:true`, mostra o rating e o tema mais fraco.

- [ ] **Step 2: Implementar.** README (raiz): seção "Táticas do Lichess" (o que é, licença CC0 do banco, como importar, onde fica o arquivo, filtros); `backend/README.md`: as rotas novas e a variável `CHESS_TRAINER_LICHESS_SOURCE`.

- [ ] **Step 3: Verificar** `npm test -- --run`, `npm run build`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src README.md backend/README.md
git commit -m "feat(taticas): configurações, cartões do painel e estatísticas por tema"
```

---

## Self-review (feito ao escrever)

- Spec §2 dados/importação → Tasks 1, 3, 4 (job); §3 seleção/conversão/Elo → Tasks 2, 4; §4 API → Task 4; §5 UI → Tasks 5–7; §6 testes → em cada task; manual no deploy.
- Nomes consistentes: `to_tactic`, `pick_next`, `record_attempt`, `theme_counts`, `tactics_status`, `theme_stats`, `elo_update`, `primary_theme`, `normalize_own_theme`, `THEME_LABELS`; rotas `/api/tactics/{status,import,next,attempts,themes}` e `/api/stats/themes`; frontend `Trainable`, `TacticOut`, `AttemptOut`, `useTacticsStatus`, `useTacticThemes`, `useThemeStats`, `useStartJob({kind:"import_lichess"})`.
- Decisão registrada: `tactics_rating` é atualizado por `set_setting` a cada tentativa (o formulário de configurações também o edita; o último a gravar vence, aceitável para uso local).
