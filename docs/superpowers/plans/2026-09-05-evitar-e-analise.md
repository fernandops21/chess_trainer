# "Evitar" completo, resultado explicado e tabuleiro de análise — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o puzzle "evitar" compreensível (linha completa até o ganho, resultado mostrando o que foi jogado e a refutação) e dar ao app um tabuleiro de análise com a engine, acessível da partida, do erro e do resultado do puzzle.

**Architecture:** Backend: o gerador ganha uma função compartilhada de "linha que materializa", usada por "punir" e "evitar"; `PuzzleOut` expõe o erro de origem e os puzzles irmãos; novo endpoint `POST /api/analyse` com engine interativa própria (lock + cache LRU). Frontend: `LineViewer` abre no lance do usuário; `ResultPanel` explica o "evitar"; novo módulo `analysis/` (`useAnalysis` + `AnalysisBoard` + página `/analise`).

**Tech Stack:** os mesmos do ciclo A (FastAPI, python-chess, SQLAlchemy; React 19 + TS + Vite, TanStack Query, chessground, chess.js, Vitest).

**Spec:** `docs/superpowers/specs/2026-09-05-evitar-completo-e-analise-design.md`

## Global Constraints

- Backend em `backend/` (`cd backend && uv run pytest -q`; hoje 154 passed + 2 warnings conhecidos do Starlette; Stockfish real presente em `backend/engines`, testes `slow` rodam com `-m "slow or not slow"`). Frontend em `frontend/` (`cd frontend && npm test && npm run typecheck && npm run build`; hoje 35 testes).
- Convenções de avaliação e regras do gerador: spec do backend §5 e §7 (materialização, alternativas só no lance final, descarte em empate, limites de tempo por busca). O "evitar" passa a obedecer exatamente às mesmas regras a partir da posição anterior ao erro.
- `end_reason` de "evitar" ∈ {`mate`, `material_gain`}; `explanation_pv` fica `[]`.
- Engine interativa: `depth = 16`, `max_seconds = 3.0`, `multipv ≤ 5`, instância separada da engine dos jobs, um pedido por vez (lock), cache LRU de 500 FENs.
- Frontend: hooks puros sem chessground; textos em português; commits em português com o trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Nunca commitar `frontend/dist`, `node_modules`, `backend/data`, `backend/engines`, `.claude/`.
- O servidor de desenvolvimento em `:8000` serve o build; não iniciar jobs de análise nem registrar revisões durante a implementação (o controlador faz a verificação manual e a regeração dos "evitar" no final).

## Estrutura de arquivos

```
backend/chess_trainer/
  core/puzzles/generator.py      + _materializing_line(); generate_avoid reescrito
  core/puzzles/service.py        + regenerate_avoid(); build_drafts passa played_uci (já passa)
  core/analysis/interactive.py   NOVO: InteractiveAnalyzer (engine própria, lock, cache)
  api/schemas.py                 + MistakeRef, PuzzleSibling em PuzzleOut; AnalyseIn/AnalyseOut/AnalyseLine
  api/routes/training.py         _puzzle_out com mistake/siblings
  api/routes/system.py           regenerate?kind=avoid
  api/routes/analysis.py         NOVO: POST /api/analyse
  api/app.py                     registra analysis.router; app.state.analyzer
backend/tests/
  test_generator_avoid.py        reescrito; test_api_training.py (+mistake/siblings); test_pipeline.py (+regenerate_avoid);
  test_api_analysis.py           NOVO
frontend/src/
  api/types.ts                   + MistakeRef, PuzzleSibling, AnalyseOut…; api/client.ts + analyse(); queries.ts + useAnalyse()
  train/LineViewer.tsx           + initialPos
  train/ResultPanel.tsx          explicação do "evitar", Explorar
  analysis/useAnalysis.ts        NOVO (puro)
  analysis/AnalysisBoard.tsx     NOVO
  pages/AnalysisPage.tsx         NOVO (/analise)
  pages/GameDetailPage.tsx       + "Explorar daqui"; pages/MistakesPage.tsx + "posicional" + Explorar
  App.tsx                        + rota /analise
frontend/tests/
  lineViewer.test.tsx (+initialPos), useAnalysis.test.ts NOVO, client.test.ts (+analyse)
```

---

### Task 1: `PuzzleOut` com o erro de origem e os puzzles irmãos

**Files:**
- Modify: `backend/chess_trainer/api/schemas.py`, `backend/chess_trainer/api/routes/training.py`
- Test: `backend/tests/test_api_training.py`

**Interfaces:**
- Produces em `PuzzleOut`: `mistake: MistakeRef` = `{ply, move_played, move_uci, eval_before, eval_after, mistake_level, mistake_by}` (da `Position` de origem) e `siblings: list[PuzzleSibling]` = `[{id, kind}]` dos **outros** puzzles da mesma `position_id`.

- [ ] **Step 1: Teste** — em `test_api_training.py`, dentro do fluxo `ready` (que tem 1 puzzle "punir" do erro do adversário no ply 6):

```python
def test_puzzle_out_carries_mistake_and_siblings(ready):
    _, client = ready
    puzzle = client.get("/api/queue").json()["items"][0]
    m = puzzle["mistake"]
    assert m["ply"] == 6 and m["move_played"] == "Nf6" and m["move_uci"] == "g8f6"
    assert m["mistake_level"] == "blunder" and m["mistake_by"] == "opponent"
    assert m["eval_before"] == 0 and m["eval_after"] < -90000
    assert puzzle["siblings"] == []
```

- [ ] **Step 2: Rodar para ver falhar** — `uv run pytest tests/test_api_training.py -q -k siblings` → KeyError.

- [ ] **Step 3: Implementar** — `schemas.py`:

```python
class MistakeRef(BaseModel):
    ply: int
    move_played: str
    move_uci: str
    eval_before: int
    eval_after: int
    mistake_level: str | None
    mistake_by: str | None


class PuzzleSibling(BaseModel):
    id: str
    kind: str
```
e em `PuzzleOut`: `mistake: MistakeRef` e `siblings: list[PuzzleSibling] = []`. Em `training.py::_puzzle_out`:

```python
        mistake=MistakeRef(ply=p.position.ply, move_played=p.position.move_played, move_uci=p.position.move_uci,
                           eval_before=p.position.eval_before, eval_after=p.position.eval_after,
                           mistake_level=p.position.mistake_level, mistake_by=p.position.mistake_by),
        siblings=[PuzzleSibling(id=s.id, kind=s.kind) for s in p.position.puzzles if s.id != p.id],
```
(`Position.puzzles` é o relacionamento já existente.)

- [ ] **Step 4: Rodar** — `uv run pytest -q` → 155 passed.
- [ ] **Step 5: Commit** — `feat: PuzzleOut expõe o erro de origem e os puzzles irmãos`

---

### Task 2: Resultado do puzzle explicado (frontend)

**Files:**
- Modify: `frontend/src/api/types.ts`, `frontend/src/train/LineViewer.tsx`, `frontend/src/train/ResultPanel.tsx`
- Test: `frontend/tests/lineViewer.test.tsx`

**Interfaces:**
- `LineViewer` ganha `initialPos?: number` (índice em `fens`, padrão último) — usado no reset quando `fenStart`/`key` mudam.
- `ResultPanel` recebe `puzzle` (com `mistake` e `siblings`) e mostra, para `avoid`: bloco "Na partida você jogou **X** (`eval_before` → `eval_after`). O melhor era **Y**." e, se houver irmão `punish`, `<LineViewer>` "O que acontecia depois de X" (solução do irmão, `keyboard={false}`, `startPly = sibling.ply + 1`). Linha principal com `initialPos = puzzle.solution.moves.length` e `startPly = kind === "avoid" ? puzzle.ply : puzzle.ply + 1`. Botão/link "Explorar" → `/analise?fen=<fen_start>&orientation=<side>&back=/treinar` (a página chega na Task 6; o link pode existir antes).

- [ ] **Step 1: Tipos** — em `types.ts`:

```ts
export interface MistakeRef { ply: number; move_played: string; move_uci: string; eval_before: number; eval_after: number; mistake_level: MistakeLevel | null; mistake_by: "me" | "opponent" | null; }
export interface PuzzleSibling { id: string; kind: PuzzleKind; }
```
e em `PuzzleOut`: `mistake: MistakeRef; siblings: PuzzleSibling[];`. Atualize os fixtures de teste (`tests/usePuzzle.test.ts` `base`, `tests/session.test.tsx` etc.) com `mistake: {...}` e `siblings: []` — o typecheck aponta cada lugar.

- [ ] **Step 2: Teste do `initialPos`** em `tests/lineViewer.test.tsx`:

```tsx
test("initialPos abre a linha na posição pedida", () => {
  render(<LineViewer fenStart="2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1" ucis={["e1e8", "c8e8", "a4e8"]} orientation="white" startPly={1} initialPos={1} keyboard={false} />);
  expect(screen.getByText("1/3")).toBeTruthy();
});
```

- [ ] **Step 3: `LineViewer`** — assinatura `({ fenStart, ucis, orientation, startPly, keyboard = true, initialPos })`; `const clamp = (n: number) => Math.max(0, Math.min(line.fens.length - 1, n));` estado inicial `useState(clamp(initialPos ?? line.fens.length - 1))`; o efeito de reset (deps `[fenStart, key]`) usa o mesmo valor. Numeração: mantém `startPly` como o ply do primeiro lance da linha.

- [ ] **Step 4: `ResultPanel`** (substituir o corpo; manter props `puzzle, review, error, onRetry, onNext, nextLabel, clockLabel, nextDisabled`):

```tsx
import { Link } from "react-router-dom";
import type { PuzzleOut, ReviewOut } from "../api/types";
import { usePuzzleQuery } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";
import { formatEval, themeLabel } from "../lib/format";
import { buildLine } from "../board/line";
import { LineViewer } from "./LineViewer";

function playedSan(p: PuzzleOut): string {
  if (p.kind !== "avoid") return p.mistake.move_played;
  return p.mistake.move_played;
}

export function ResultPanel({ puzzle, review, error, onRetry, onNext, nextLabel = "Próximo puzzle", clockLabel, nextDisabled }: {...}) {
  const ucis = puzzle.solution.moves.map((m) => m.uci);
  const isAvoid = puzzle.kind === "avoid";
  const startPly = isAvoid ? puzzle.ply : puzzle.ply + 1;
  const bestSan = buildLine(puzzle.fen_start, ucis.slice(0, 1)).sans[0] ?? ucis[0];
  const punishSibling = isAvoid ? puzzle.siblings.find((s) => s.kind === "punish") : undefined;
  const { data: refutation } = usePuzzleQuery(punishSibling?.id ?? null);
  const clean = review && review.result === "correct" && !review.used_hint;
  const exploreHref = `/analise?fen=${encodeURIComponent(puzzle.fen_start)}&orientation=${puzzle.side_to_move}&back=${encodeURIComponent("/treinar")}`;
  return (
    <div className="two-col">
      <div>
        <LineViewer fenStart={puzzle.fen_start} ucis={ucis} orientation={puzzle.side_to_move} startPly={startPly} initialPos={puzzle.solution.moves.length} />
        {isAvoid && refutation && (
          <div className="card" style={{ marginTop: 12 }}>
            <b>O que acontecia depois de {playedSan(puzzle)}</b>
            <LineViewer fenStart={refutation.fen_start} ucis={refutation.solution.moves.map((m) => m.uci)} orientation={puzzle.side_to_move} startPly={refutation.ply + 1} initialPos={0} keyboard={false} />
          </div>
        )}
      </div>
      <div className="card">
        {clockLabel && <div className="muted">{clockLabel}</div>}
        {error && (<><ErrorBox error={error} /><button onClick={onRetry}>Tentar registrar de novo</button></>)}
        {review && (<>
          <div className={`msg ${clean ? "ok" : "bad"}`}>{clean ? "Resolvido sem erro." : "Concluído, mas contou como erro (volta em 1 dia)."}</div>
          <div className="muted">Próxima revisão em {review.interval_days} dia(s) · facilidade {review.ease} · lapsos {review.lapses}{review.is_leech ? " · virou sanguessuga" : ""}</div>
        </>)}
        {isAvoid && (
          <p>Na partida você jogou <b>{playedSan(puzzle)}</b> ({formatEval(puzzle.mistake.eval_before)} → {formatEval(puzzle.mistake.eval_after)}). O melhor era <b>{bestSan}</b>.</p>
        )}
        <div style={{ marginTop: 10 }}><span className="tag">{themeLabel(puzzle.theme)}</span><span className="tag">{puzzle.category}</span><span className="tag">{puzzle.end_reason === "mate" ? "termina em mate" : "ganho de material"}</span></div>
        <div className="row" style={{ marginTop: 10 }}>
          <a href={puzzle.game.source_id} target="_blank" rel="noopener noreferrer">partida no chess.com</a>
          <Link to={`/partidas/${puzzle.game.id}?ply=${puzzle.ply}`}>partida no app</Link>
          <Link to={exploreHref}>Explorar</Link>
          {review && <button className="primary" style={{ marginLeft: "auto" }} onClick={onNext} disabled={nextDisabled}>{nextDisabled ? "Carregando…" : nextLabel}</button>}
        </div>
      </div>
    </div>
  );
}
```
(Ajuste ao que já existe no arquivo: `clockLabel`/`nextDisabled` vieram das correções da revisão; `playedSan` pode ser inlined.)

- [ ] **Step 5: Verificar** — `npm test && npm run typecheck && npm run build`. Abrir um resultado de puzzle no build servido: a linha abre no seu lance; ▶ avança.
- [ ] **Step 6: Commit** — `fix: resultado do puzzle abre no lance do usuário e explica o "evitar"`

---

### Task 3: "Evitar" como linha completa e regeração só dos "evitar"

**Files:**
- Modify: `backend/chess_trainer/core/puzzles/generator.py`, `backend/chess_trainer/core/puzzles/service.py`, `backend/chess_trainer/api/routes/system.py`, spec do backend §7.2
- Test: `backend/tests/test_generator_avoid.py` (reescrever), `backend/tests/test_pipeline.py` (+2), `backend/tests/test_api_system.py` (+1)

**Interfaces:**
- `generator._materializing_line(board, engine, cfg, first_lines, mate_mode, target) -> PuzzleDraft | None`: o laço atual de `generate_punish` (do primeiro lance até a materialização), recebendo a primeira análise já feita. `generate_punish` passa a: analisar, decidir `mate_mode`/`target` (com a pré-checagem da PV e o `min_solver_eval_cp`), chamar `_materializing_line`.
- `generate_avoid(board_before, engine, cfg, played_uci=None) -> PuzzleDraft | None`: analisa multipv 3; se `best.move == played_uci` → None; `gap = best.score - second.score` (se `best` é mate a favor e `second` não, `gap = 10**6`; se só há uma linha, None); se `gap < cfg.avoid_gap_cp` → None; `mate_mode = is_mate_for(best.score)`; senão exige `best.score >= cfg.min_solver_eval_cp` e `target = floor_to_piece(min(clamp(gap), clamp(best.score)) / 100)`, `target <= 0` → None; devolve `_materializing_line(...)` (com a mesma pré-checagem da PV do "punir").
- `service.regenerate_avoid(db, engine, settings, progress=None, should_stop=None) -> int`: apaga `Review` dos puzzles `kind == "avoid"` e esses puzzles; para cada partida analisada (recentes primeiro), para cada posição com `mistake_by == "me"`, gera só o "evitar" (dedup por `fen_start + kind`), commit por partida, tolera `EngineError`, respeita `should_stop`.
- `POST /api/puzzles/regenerate?kind=avoid` chama `regenerate_avoid`; sem `kind`, `regenerate_all`.

- [ ] **Step 1: Testes** — `tests/test_generator_avoid.py` (substituir):

```python
import chess
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.puzzles.generator import PuzzleConfig, generate_avoid
from tests.fakes import FakeEngine, first_legal_default

CFG = PuzzleConfig(depth=10, avoid_gap_cp=150)
M = MATE_SCORE
# Posição antes do erro: brancas jogam; Nxd5 ganha a dama (o usuário jogou outra coisa na partida)
BEFORE = "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1"


def _after(fen, *ucis):
    b = chess.Board(fen)
    for u in ucis: b.push_uci(u)
    return b


def test_avoid_runs_the_line_to_material_gain():
    fake = FakeEngine({
        chess.Board(BEFORE).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7")), LineEval("e1e2", 0, ("e1e2",))],
        _after(BEFORE, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    d = generate_avoid(chess.Board(BEFORE), fake, CFG, played_uci="e1e2")
    assert d is not None and d.end_reason == "material_gain" and d.solver_moves == 1
    assert [m.uci for m in d.moves] == ["c3d5"] and d.explanation_pv == []


def test_avoid_not_generated_when_best_is_the_played_move():
    fake = FakeEngine({chess.Board(BEFORE).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7")), LineEval("e1e2", 0, ("e1e2",))]})
    assert generate_avoid(chess.Board(BEFORE), fake, CFG, played_uci="c3d5") is None


def test_avoid_not_generated_when_gap_is_small():
    fake = FakeEngine({chess.Board(BEFORE).epd(): [LineEval("c3d5", 300, ("c3d5",)), LineEval("e1e2", 200, ("e1e2",))]})
    assert generate_avoid(chess.Board(BEFORE), fake, CFG) is None


def test_avoid_not_generated_without_materialization():
    fake = FakeEngine(default=first_legal_default(400))  # +4 "posicional": nunca captura
    assert generate_avoid(chess.Board("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"), fake, CFG) is None


def test_avoid_mate_mode_runs_to_checkmate():
    MATE = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1"
    fake = FakeEngine({
        chess.Board(MATE).epd(): [LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8")), LineEval("a4a7", 100, ("a4a7",))],
        _after(MATE, "e1e8").epd(): [LineEval("c8e8", -(M - 1), ("c8e8",))],
        _after(MATE, "e1e8", "c8e8").epd(): [LineEval("a4e8", M - 1, ("a4e8",))],
    })
    d = generate_avoid(chess.Board(MATE), fake, CFG, played_uci="a4a7")
    assert d is not None and d.end_reason == "mate" and d.solver_moves == 2
```

Em `tests/test_pipeline.py`:

```python
def test_regenerate_avoid_keeps_punish_and_its_reviews(db_session):
    # partida com um erro MEU que gera punish (do lado do adversário) e avoid (do meu lado)
    ...  # monte com _game(pgn=SCHOLAR, my_color="black") e um FakeEngine cujo script gera os dois puzzles no ply 6 (Nf6 é o erro das pretas: my_color="black" → mistake_by="me")
    analyze_pending(db_session, engine, SETTINGS)
    punish = db_session.scalars(select(Puzzle).where(Puzzle.kind == "punish")).one()
    db_session.add(Review(puzzle_id=punish.id, result="correct", ease=2.5, interval_days=1, due_at=punish.created_at, lapses=0)); db_session.commit()
    n = regenerate_avoid(db_session, engine, SETTINGS)
    assert db_session.scalar(select(func.count(Review.id))) == 1          # revisão do punish preservada
    assert db_session.scalar(select(Puzzle.id).where(Puzzle.kind == "punish")) == punish.id
    assert n == db_session.scalar(select(func.count(Puzzle.id)).where(Puzzle.kind == "avoid"))
```
(Para o "avoid" existir no cenário do mate pastor com `my_color="black"`: script a posição antes de Nf6 (pretas a jogar) com `LineEval("g8f6"...)`? Não: o melhor deve ser diferente do jogado e materializar. Use antes de 6...Nf6 a linha `LineEval("g7g6", 50, ...)`? Não materializa. Mais simples: escolha um script em que o "avoid" NÃO é gerado e assert `n == 0`, mantendo as demais asserções — o objetivo do teste é a preservação do "punir" e das revisões. Documente a escolha no relatório.)

Em `tests/test_api_system.py`:

```python
def test_regenerate_kind_avoid_route(client, app):
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import"); app.state.jobs.wait()
    r = client.post("/api/puzzles/regenerate", params={"kind": "avoid"})
    assert r.status_code == 202 and r.json()["job"] == "regenerate"
    app.state.jobs.wait()
    assert app.state.jobs.snapshot()["state"] == "idle"
    assert client.post("/api/puzzles/regenerate", params={"kind": "xyz"}).status_code == 422
```

- [ ] **Step 2: Rodar para ver falhar.**
- [ ] **Step 3: Implementar** — refatore `generate_punish` extraindo o laço para `_materializing_line(board, engine, cfg, lines, mate_mode, target)` (mesmo corpo de hoje a partir de `limit = ...`). `generate_avoid` conforme as Interfaces (mate a favor em `best` com `second` não-mate → gap infinito; use `_pv_never_materializes` antes do laço, como o punir). `service.build_drafts` já passa `pos.move_uci` para `generate_avoid`. `service.regenerate_avoid` espelhando `regenerate_all` (mesma estrutura de fases: apagar, para cada partida: drafts só de `avoid` para posições `mistake_by == "me"`, `persist_drafts`, commit; `EngineError` → rollback + restart + continue; `should_stop` entre partidas). Rota: `def post_regenerate(request, kind: Literal["avoid"] | None = None)` escolhe a função.
- Spec do backend §7.2: substituir o texto do "evitar" pela regra nova (uma frase para cada condição) e anotar `explanation_pv` vazio.
- [ ] **Step 4: Rodar** — `uv run pytest -q -m "slow or not slow"` → tudo verde.
- [ ] **Step 5: Commit** — `feat: puzzle evitar joga a linha até o ganho; regeração só dos evitar`

---

### Task 4: `POST /api/analyse` com engine interativa

**Files:**
- Create: `backend/chess_trainer/core/analysis/interactive.py`, `backend/chess_trainer/api/routes/analysis.py`, `backend/tests/test_api_analysis.py`
- Modify: `backend/chess_trainer/api/schemas.py`, `backend/chess_trainer/api/app.py`

**Interfaces:**
- `interactive.InteractiveAnalyzer(engine_factory: Callable[[], EngineLike | None], depth=16, max_seconds=3.0, cache_size=500)`: `analyse(fen: str, multipv: int = 3) -> AnalysisResult` onde `AnalysisResult = {fen, turn, terminal: str | None, lines: [{move, san, score, pv, pv_san}]}` (dict simples). Valida o FEN (`ValueError` se inválido); posição terminal → `lines: []`, `terminal ∈ {"checkmate","stalemate","draw"}`; cria a engine na primeira chamada (`RuntimeError("engine indisponível")` se a fábrica devolve `None`); `threading.Lock` em volta da chamada; cache `OrderedDict` por `(fen, multipv)`; `close()`.
- Rota `POST /api/analyse` body `AnalyseIn {fen: str, multipv: int = 3 (1..5)}` → `AnalyseOut {fen, turn, terminal, lines: list[AnalyseLine]}`; 400 FEN inválido; 503 engine indisponível. `create_app` recebe `analysis_engine_factory=None` (padrão: `lambda: default_engine_factory(load_settings(db))` com uma sessão própria) e guarda `app.state.analyzer = InteractiveAnalyzer(...)`.

- [ ] **Step 1: Testes** `tests/test_api_analysis.py`:

```python
import chess
from fastapi.testclient import TestClient
from chess_trainer.api.app import create_app
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.analysis.interactive import InteractiveAnalyzer
from chess_trainer.core.evals import MATE_SCORE
from tests.fakes import FakeEngine, first_legal_default

MATE_IN_1 = "6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1"


def _engine():
    return FakeEngine({chess.Board(MATE_IN_1).epd(): [LineEval("a1a8", MATE_SCORE - 1, ("a1a8",))]}, first_legal_default(20))


def test_analyzer_lines_with_san_and_cache():
    fake = _engine()
    az = InteractiveAnalyzer(lambda: fake, depth=8, max_seconds=1.0)
    r = az.analyse(MATE_IN_1)
    assert r["turn"] == "white" and r["terminal"] is None
    assert r["lines"][0]["move"] == "a1a8" and r["lines"][0]["san"] == "Ra8#" and r["lines"][0]["score"] == MATE_SCORE - 1
    assert r["lines"][0]["pv_san"] == ["Ra8#"]
    az.analyse(MATE_IN_1)
    assert len(fake.calls) == 1            # cache
    assert fake.max_seconds[0] == 1.0 and fake.depths[0] == 8


def test_analyzer_terminal_and_invalid():
    import pytest
    az = InteractiveAnalyzer(lambda: _engine())
    mated = az.analyse("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert mated["terminal"] == "checkmate" and mated["lines"] == []
    with pytest.raises(ValueError):
        az.analyse("isto nao e fen")


def test_analyse_route():
    app = create_app(db_path=":memory:", analysis_engine_factory=lambda: _engine())
    client = TestClient(app)
    r = client.post("/api/analyse", json={"fen": MATE_IN_1})
    assert r.status_code == 200 and r.json()["lines"][0]["san"] == "Ra8#"
    assert client.post("/api/analyse", json={"fen": "xx"}).status_code == 400
    assert client.post("/api/analyse", json={"fen": MATE_IN_1, "multipv": 9}).status_code == 422


def test_analyse_route_without_engine_is_503():
    client = TestClient(create_app(db_path=":memory:", analysis_engine_factory=lambda: None))
    assert client.post("/api/analyse", json={"fen": MATE_IN_1}).status_code == 503
```

- [ ] **Step 2: Rodar para ver falhar.**
- [ ] **Step 3: Implementar `core/analysis/interactive.py`**

```python
import threading
from collections import OrderedDict
from typing import Callable

import chess

from chess_trainer.core.analysis.engine import EngineLike


class InteractiveAnalyzer:
    def __init__(self, engine_factory: Callable[[], EngineLike | None], depth: int = 16, max_seconds: float = 3.0, cache_size: int = 500):
        self._factory = engine_factory
        self._engine: EngineLike | None = None
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple[str, int], dict] = OrderedDict()
        self.depth, self.max_seconds, self.cache_size = depth, max_seconds, cache_size

    def _ensure_engine(self) -> EngineLike:
        if self._engine is None:
            self._engine = self._factory()
            if self._engine is None:
                raise RuntimeError("engine indisponível")
        return self._engine

    @staticmethod
    def _terminal(board: chess.Board) -> str | None:
        if board.is_checkmate(): return "checkmate"
        if board.is_stalemate(): return "stalemate"
        if board.is_game_over(): return "draw"
        return None

    def analyse(self, fen: str, multipv: int = 3) -> dict:
        board = chess.Board(fen)            # ValueError se inválido
        key = (board.fen(), multipv)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            result = {"fen": board.fen(), "turn": "white" if board.turn else "black", "terminal": self._terminal(board), "lines": []}
            if result["terminal"] is None:
                engine = self._ensure_engine()
                for line in engine.analyse(board, self.depth, multipv=multipv, max_seconds=self.max_seconds):
                    b = board.copy(); pv_san = []
                    for uci in line.pv:
                        try: pv_san.append(b.san(b.push_uci(uci) or chess.Move.from_uci(uci)))
                        except Exception: break
                    # (o push_uci devolve o Move; san() precisa da posição ANTES do lance — use: mv = chess.Move.from_uci(uci); san = b.san(mv); b.push(mv))
                    result["lines"].append({"move": line.move, "san": pv_san[0] if pv_san else line.move, "score": line.score, "pv": list(line.pv), "pv_san": pv_san})
            self._cache[key] = result
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return result

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close(); self._engine = None
```
Escreva o laço de SAN corretamente: `mv = chess.Move.from_uci(uci); if mv not in b.legal_moves: break; pv_san.append(b.san(mv)); b.push(mv)`.

- [ ] **Step 4: Schemas, rota e app** — `schemas.py`: `AnalyseIn(fen: str, multipv: int = Field(3, ge=1, le=5))`, `AnalyseLine(move, san, score, pv: list[str], pv_san: list[str])`, `AnalyseOut(fen, turn, terminal: str | None, lines: list[AnalyseLine])`. `routes/analysis.py`:

```python
router = APIRouter(prefix="/api")

@router.post("/analyse", response_model=AnalyseOut)
def post_analyse(body: AnalyseIn, request: Request):
    try:
        return request.app.state.analyzer.analyse(body.fen, body.multipv)
    except ValueError:
        raise HTTPException(400, "FEN inválido")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except chess.engine.EngineError as exc:
        raise HTTPException(503, f"engine falhou: {exc}")
```
`app.py`: parâmetro `analysis_engine_factory=None`; padrão:

```python
    def _default_analysis_factory():
        db = app.state.session_factory()
        try:
            return default_engine_factory(load_settings(db))
        finally:
            db.close()
    app.state.analyzer = InteractiveAnalyzer(analysis_engine_factory or _default_analysis_factory)
    app.include_router(analysis.router)
```
- [ ] **Step 5: Rodar** `uv run pytest -q` → verde. **Slow**: acrescente em `test_engine.py` um teste `slow` que usa `InteractiveAnalyzer(lambda: StockfishEngine(path))` em `MATE_IN_1` e espera `san == "Ra8#"`.
- [ ] **Step 6: Commit** — `feat: endpoint de análise interativa com engine própria e cache`

---

### Task 5: Tabuleiro de análise (frontend)

**Files:**
- Create: `frontend/src/analysis/useAnalysis.ts`, `frontend/src/analysis/AnalysisBoard.tsx`, `frontend/src/pages/AnalysisPage.tsx`, `frontend/tests/useAnalysis.test.ts`
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/App.tsx`, `frontend/src/board/Board.tsx` (setas), `frontend/tests/client.test.ts`

**Interfaces:**
- Tipos: `AnalyseLine {move, san, score, pv: string[], pv_san: string[]}`, `AnalyseOut {fen, turn, terminal: string | null, lines: AnalyseLine[]}`. `api.analyse(fen, multipv = 3)` → `POST /api/analyse`. `useAnalyse(fen: string | null)` → `useQuery({ queryKey: ["analyse", fen], queryFn, enabled: !!fen, staleTime: Infinity, retry: 0 })`.
- `useAnalysis(fenStart)`: `{ fens: string[]; sans: string[]; index: number; fen: string; turn: "white"|"black"; dests: Map<Key, Key[]>; play(uci: string): boolean; playLine(ucis: string[]): void; undo(): void; reset(): void; goTo(i: number): void; lastMove?: [Key,Key] }`. `play` ignora lances ilegais (devolve `false`); jogar a partir de um ponto no meio da pilha descarta o futuro. `playLine` aplica os lances um a um com `setTimeout` de 250 ms entre eles (parâmetro `stepMs`, default 250, injetável para teste).
- `Board` ganha `arrows?: {orig: Key; dest: Key; brush?: string}[]` mapeados em `drawable.autoShapes` (junto com `highlight`).
- `AnalysisBoard({ fenStart, orientation, backTo })`: layout `two-col`; esquerda o `Board` (ambos os lados jogáveis: `movableColor = turn`), abaixo os botões ⏮ ◀ inverter e "Voltar" (`Link to={backTo}`); direita: avaliação grande (`formatEval` do POV das brancas: se `turn === "black"` negue o score para mostrar sempre do ponto de vista das brancas, com rótulo), "analisando…" enquanto `isFetching`, as linhas (`pv_san` unidas com espaço, clicável → `playLine(line.pv)`), `ErrorBox` em erro, e a lista dos lances explorados (`sans`, clique → `goTo`). Posição terminal: mostrar "Xeque-mate"/"Afogamento"/"Empate".
- `AnalysisPage`: lê `fen`, `orientation` (padrão `white`), `back` (padrão `/`) dos search params; FEN ausente/ inválido (chess.js lança) → mensagem e link para o Painel. Rota `/analise` em `App.tsx` (a `Nav` continua visível).

- [ ] **Step 1: Testes** — `tests/useAnalysis.test.ts`:

```ts
import { act, renderHook } from "@testing-library/react";
import { useAnalysis } from "../src/analysis/useAnalysis";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

test("play/undo/reset e ilegal ignorado", () => {
  const { result } = renderHook(() => useAnalysis(START));
  expect(result.current.play("e2e5")).toBe(false);
  act(() => { result.current.play("e2e4"); });
  act(() => { result.current.play("e7e5"); });
  expect(result.current.sans).toEqual(["e4", "e5"]);
  expect(result.current.turn).toBe("white");
  act(() => result.current.undo());
  expect(result.current.sans).toEqual(["e4"]);
  act(() => { result.current.play("c7c5"); });
  expect(result.current.sans).toEqual(["e4", "c5"]);
  act(() => result.current.goTo(1));
  expect(result.current.fen.split(" ")[1]).toBe("b");
  act(() => { result.current.play("d7d5"); });     // descarta o futuro (c5)
  expect(result.current.sans).toEqual(["e4", "d5"]);
  act(() => result.current.reset());
  expect(result.current.sans).toEqual([]) ;
  expect(result.current.fen).toBe(START);
});

test("playLine aplica os lances em sequência", () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useAnalysis(START, { stepMs: 10 }));
  act(() => result.current.playLine(["e2e4", "e7e5", "g1f3"]));
  act(() => { vi.advanceTimersByTime(50); });
  expect(result.current.sans).toEqual(["e4", "e5", "Nf3"]);
  vi.useRealTimers();
});
```
E em `tests/client.test.ts`: `api.analyse(fen)` faz `POST /api/analyse` com `{fen, multipv: 3}`.

- [ ] **Step 2: Implementar** `useAnalysis.ts` (chess.js; estado `{ fens, sans, index }`; `dests` via `destsFrom`), `AnalysisBoard.tsx`, `AnalysisPage.tsx`, `Board` com `arrows`, cliente/tipos/query, rota. Estilos: `.eval-big { font-size: 32px; font-weight: 700; }`, `.pvline { display:block; text-align:left; min-height: var(--tap); }`.
- [ ] **Step 3: Verificar** — `npm test && npm run typecheck && npm run build`; no build servido, abrir `/analise?fen=<fen de um puzzle>&orientation=white&back=/treinar`: jogar lances, ver avaliação/linhas, clicar numa linha, desfazer, voltar.
- [ ] **Step 4: Commit** — `feat: tabuleiro de análise com engine (página /analise)`

---

### Task 6: Entradas do "Explorar" e etiqueta "posicional"; verificação e regeração

**Files:**
- Modify: `frontend/src/pages/GameDetailPage.tsx`, `frontend/src/pages/MistakesPage.tsx`, `frontend/src/train/TrainPage.tsx` (opcional: `back` do resultado), `README.md`

- [ ] **Step 1** — `GameDetailPage`: botão "Explorar daqui" ao lado da navegação → `/analise?fen=<fen atual>&orientation=<my_color>&back=/partidas/<id>?ply=<current>`.
- [ ] **Step 2** — `MistakesPage`: na ficha (`MistakeDetail`) botão "Explorar" → `/analise?fen=<m.fen>&orientation=<m.my_color>&back=/erros`; nos itens da lista, quando `m.puzzles.length === 0` e `m.mistake_by === "me"`, etiqueta `<span className="tag">posicional</span>` (texto curto "sem puzzle: posicional ou trivial" no detalhe).
- [ ] **Step 3** — README raiz: uma linha sobre o tabuleiro de análise.
- [ ] **Step 4** — `npm test && npm run typecheck && npm run build`; commit `feat: Explorar a partir da partida e da revisão de erros; etiqueta posicional`.
- [ ] **Step 5 (controlador)** — reiniciar o servidor no código novo; `POST /api/puzzles/regenerate?kind=avoid`; verificar no navegador: um "evitar" novo (linha completa), o resultado com "o que você jogou" e a refutação, Explorar do resultado, da partida e do erro; celular 375 px na página de análise.

---

## Self-review (feito ao escrever)

- Spec §2 → Tasks 1–2; §3 → Task 3; §4.1 → Task 4; §4.2 → Tasks 5–6; §5 testes distribuídos; regeração e verificação manual na Task 6.
- Consistência: `PuzzleOut.mistake/siblings` (T1) consumidos em T2; `usePuzzleQuery` já existe; `generate_avoid(board, engine, cfg, played_uci)` mantém a assinatura atual (T3); `InteractiveAnalyzer` (T4) usa `EngineLike.analyse(..., max_seconds=)` já existente; `Board.arrows` (T5) é aditivo.
- Riscos: o teste de `regenerate_avoid` no cenário do mate pastor pode não produzir "evitar" (documentado); `playLine` com timers em teste usa `stepMs` injetável; `useAnalyse` com `staleTime: Infinity` evita reanálise ao voltar.
