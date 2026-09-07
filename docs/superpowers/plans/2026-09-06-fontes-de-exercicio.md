# Fontes de exercício (ciclo B1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma fila única de repetição com fonte (`own`, `lichess`, `study`), botões guardar/tirar, importação de estudos do Lichess como exercícios, último lance do adversário animado e marcações com o botão direito.

**Architecture:** `Puzzle` ganha `source`/`in_queue`/`external_id`/`chapter_id`/`fen_before`/`last_move` com `position_id`/`game_id` opcionais, via `migrate()` idempotente em `core/db.py`. Novo pacote `core/studies/` (parser de PGN do Lichess com python-chess → capítulos + solução; serviço de import/reimport) e rotas `api/routes/studies.py`. Frontend: `PuzzleOut` com campos opcionais, `usePuzzle` com fase de introdução (animação do último lance), `Board` com `drawable`, tela Estudos, fontes na sessão.

**Tech Stack:** Python 3.13 (`uv`), FastAPI, SQLAlchemy 2 + SQLite, python-chess (`chess.pgn`), httpx; React 19 + TS, TanStack Query, chessground, chess.js, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-06-fontes-de-exercicio-design.md`

## Global Constraints

- Texto de interface em português do Brasil; nunca "regerar/regeração" (usar "recriar").
- Nada apaga ou reescreve puzzles/revisões existentes: migração só adiciona colunas com padrão (`source='own'`, `in_queue=1`) e tabelas novas; `DELETE /api/studies/{id}` apaga apenas o que o estudo criou.
- `utcnow()` naive UTC; "hoje" via `local_day_start`.
- Trabalho de rede (baixar PGN) no `JobRunner`; sem rede em testes (`httpx.MockTransport` ou PGN de fixture).
- Backend: `cd backend && uv run pytest -q` verde (213 hoje; 2 warnings conhecidos). Frontend: testes só em `frontend/tests/**`, sem jest-dom; `npm test -- --run` (74 hoje), `npx tsc --noEmit -p .`, `npm run build` verdes.
- `usePuzzle`: uma instância por puzzle, remontar com `key={puzzle.id}`.
- Commits em português, conventional, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, via `git commit -F` com arquivo UTF-8 em `.superpowers/`; `git add` com caminhos explícitos.
- Formato da solução (`Puzzle.solution` JSON): `{"moves": [{"uci","by":"solver|engine","alternatives":[]}], "explanation_pv": [], "wrong_moves": {uci: str}?, "comments": {"<idx>": str}?, "shapes": {"<idx>": [{"orig","dest"?,"brush"}]}?, "intro": str?}` — índices de `comments`/`shapes` são o índice do lance em `moves` (0 = após o primeiro lance); `"0"` em `shapes` é mostrado na posição inicial do puzzle. (Decisão: `intro` vive dentro de `solution` para não mexer em colunas; o capítulo também guarda `intro_comment`.)
- Fixture real: `backend/tests/fixtures/study_4JKVAfaE.pgn` (27 capítulos; a maioria `[ChapterMode "gamebook"]`).

---

## File map

Backend (`backend/chess_trainer/`):
- Modify `core/models.py` (Puzzle: colunas novas; `Study`, `StudyChapter`), `core/db.py` (`migrate`), `core/srs/queue.py` (`sources`, `study_id`, outer join), `api/schemas.py`, `api/routes/training.py` (`_puzzle_out`, queue params, `/puzzles/{id}/queue`, dashboard `by_source`), `api/routes/tactics.py` (`/tactics/{id}/save`, `TacticOut.saved`), `api/routes/games.py` (`PuzzleRef.in_queue`), `api/app.py` (router studies).
- Create `core/studies/__init__.py`, `core/studies/parser.py`, `core/studies/service.py`, `api/routes/studies.py`.
- Tests: `tests/test_migration.py`, `tests/test_srs_queue.py` (append), `tests/test_api_training.py` (append), `tests/test_api_tactics.py` (append), `tests/test_study_parser.py`, `tests/test_study_service.py`, `tests/test_api_studies.py`.

Frontend (`frontend/src/`):
- Modify `api/types.ts`, `api/client.ts`, `api/queries.ts`, `board/Board.tsx`, `train/usePuzzle.ts`, `train/PuzzleView.tsx`, `train/ResultPanel.tsx`, `train/TacticResultPanel.tsx`, `train/LineViewer.tsx`, `train/SessionStart.tsx`, `train/TrainPage.tsx`, `train/SessionSummary.tsx`, `analysis/AnalysisBoard.tsx`, `pages/MistakesPage.tsx`, `pages/DashboardPage.tsx`, `components/Nav.tsx`, `components/JobCard.tsx`, `App.tsx`, `lib/format.ts`.
- Create `pages/StudiesPage.tsx`, `pages/StudyDetailPage.tsx`, `train/QueueButtons.tsx`.
- Tests em `frontend/tests/`.

---

### Task 1: Migração, modelos de estudo e fila por fonte

**Files:**
- Modify: `backend/chess_trainer/core/models.py`, `backend/chess_trainer/core/db.py`, `backend/chess_trainer/core/srs/queue.py`
- Test: `backend/tests/test_migration.py` (create), `backend/tests/test_srs_queue.py` (append), `backend/tests/test_models.py` (append)

**Interfaces:**
- Produces: `Puzzle.source: str = "own"`, `Puzzle.in_queue: bool = True`, `Puzzle.external_id: str | None` (índice único parcial via `UniqueConstraint` simples — SQLite aceita múltiplos NULL), `Puzzle.chapter_id: str | None` (FK `study_chapters.id`), `Puzzle.fen_before: str | None`, `Puzzle.last_move: str | None`; `Puzzle.position_id`/`game_id` opcionais; `__table_args__ = (UniqueConstraint("fen_start", "kind", "source", name="uq_puzzle_fen_kind_source"),)`.
- `Study(id, title, author, source_url, lichess_id (único, opcional), imported_at, created_at, updated_at)` com `chapters` (relationship, `order_by="StudyChapter.order"`, cascade delete); `StudyChapter(id, study_id, order, name, lichess_url (único, opcional), fen, orientation, mode, pgn, intro_comment, puzzle_id (FK puzzles.id, opcional), in_queue)`, relationship `puzzle`.
- `migrate(engine)` em `core/db.py`, chamada por `init_db` após `create_all`: para cada coluna nova ausente em `puzzles` (ver `PRAGMA table_info(puzzles)`), `ALTER TABLE puzzles ADD COLUMN …` com o padrão; cria `CREATE UNIQUE INDEX IF NOT EXISTS uq_puzzle_fen_kind_source ON puzzles(fen_start, kind, source)` e `CREATE UNIQUE INDEX IF NOT EXISTS uq_puzzle_external_id ON puzzles(external_id)` (NULLs não colidem). Idempotente.
- `QueueFilters` ganha `sources: tuple[str, ...] = ()` e `study_id: str | None = None`; `build_queue` filtra `Puzzle.in_queue.is_(True)`, aplica `sources`/`study_id` (via `Puzzle.chapter_id.in_(select(StudyChapter.id).where(StudyChapter.study_id == study_id))`), e ordena os novos por `func.coalesce(Game.played_at, Puzzle.created_at).desc()` com `outerjoin(Game)`.

- [ ] **Step 1: Teste de migração (falha)** — `tests/test_migration.py`: cria um banco em arquivo (`tmp_path/"old.db"`) executando SQL cru do esquema antigo de `puzzles` (colunas até `srs_last_reviewed_at`, `UNIQUE(fen_start, kind)`), mais `games`/`positions`/`reviews`/`settings` mínimos (copiar do `CREATE TABLE` atual via `sqlite3` na própria fixture: gere o esquema com `Base.metadata.create_all` de um metadata SEM as colunas novas? Mais simples: string SQL literal no teste com as colunas antigas), insere um puzzle antigo; chama `make_engine(path)` + `init_db(engine)`; abre sessão e afirma `db.get(Puzzle, id).source == "own"`, `in_queue is True`, `fen_before is None`; chama `init_db` de novo (idempotente); afirma que `Study`/`StudyChapter` existem (insere um).
- [ ] **Step 2: Modelos e migração** — implementar conforme Interfaces. Em `Study`/`StudyChapter`, `String(36)` ids com `new_id`, `mode: String(8)`, `orientation: String(5)`, `pgn: Text`, `intro_comment: Text default ""`, `in_queue: Boolean default True`.
- [ ] **Step 3: Testes da fila (falham)** — em `tests/test_srs_queue.py` (usar `make_puzzle` de `tests/factories.py`, que cria puzzles `own`; para `lichess`/`study` criar `Puzzle` direto com `position_id=None, game_id=None`): (a) `in_queue=False` não aparece nem em `due` nem em `new` nem nos contadores; (b) `sources=("lichess",)` devolve só esses; (c) `study_id` devolve só os capítulos daquele estudo; (d) novos sem `game` ordenados por `created_at` junto dos `own` por `played_at` (coalesce).
- [ ] **Step 4: Fila** — implementar; rodar toda a suíte (`uv run pytest -q`).
- [ ] **Step 5: Commit** — `feat(fontes): puzzles com fonte e fila, modelos de estudo e migração idempotente`.

---

### Task 2: `PuzzleOut` com fonte e último lance; guardar/tirar; salvar tática; painel por fonte

**Files:**
- Modify: `backend/chess_trainer/api/schemas.py`, `backend/chess_trainer/api/routes/training.py`, `backend/chess_trainer/api/routes/tactics.py`, `backend/chess_trainer/api/routes/games.py`
- Test: `backend/tests/test_api_training.py` (append), `backend/tests/test_api_tactics.py` (append)

**Interfaces:**
- `PuzzleOut`: `source: str`, `in_queue: bool`, `fen_before: str | None`, `last_move: str | None`, `study: StudyRef | None` (`StudyRef(id, title, chapter_id, chapter_name, lichess_url: str | None)`), `game: GameRef | None`, `mistake: MistakeRef | None`, `ply: int | None`, `move_played: str | None`. `PuzzleRef` ganha `in_queue: bool`.
- `_puzzle_out(db, p)`: último lance — `own` punir: `p.position.fen`, `p.position.move_uci`; `own` evitar: posição da mesma partida com `ply == p.position.ply - 1` (query) → `fen`, `move_uci`, senão nulos; `lichess`/`study`: colunas `fen_before`/`last_move`.
- `GET /api/queue?sources=own,lichess&study_id=`; `POST /api/puzzles/{id}/queue {in_queue: bool}` → `PuzzleOut`; `GET /api/dashboard` ganha `by_source: {own: {in_queue, due}, lichess: {...}, study: {...}}` (due = `srs_due_at <= now` e `in_queue`).
- `POST /api/tactics/{lichess_id}/save` → 201 `PuzzleOut` (idempotente: 200 com o existente; se existia com `in_queue=False`, volta para `True`). Cria `Puzzle(source="lichess", kind="punish", external_id=id, fen_start=t.fen_start, side_to_move, solution=json(t.solution), end_reason, theme=t.theme, category="lichess", solver_moves, fen_before=row.fen, last_move=row.moves.split()[0])`. `TacticOut.saved: bool` (existe puzzle com `external_id` e `in_queue`).
- `get_puzzle`/`post_review` funcionam para qualquer fonte (`record_review` não depende de game).

- [ ] **Step 1: Testes (falham)** — `test_api_training.py`: puzzle `own` evitar devolve `fen_before`/`last_move` do ply anterior (criar duas `Position`s consecutivas) e punir devolve o do próprio; `POST /puzzles/{id}/queue {in_queue:false}` some da fila e do `by_source.own.in_queue`; voltar reaparece. `test_api_tactics.py`: após `run_import`, `POST /tactics/00sHx/save` → 201 com `source == "lichess"`, `fen_before` igual à FEN do banco e `last_move == "e8d7"`, `game is None`; segundo POST → 200 mesmo id; `GET /tactics/next` (rating 1760, janela 50) devolve `saved: true`; `GET /queue?sources=lichess` lista o puzzle; `POST /reviews` nele funciona.
- [ ] **Step 2: Implementar.** Atenção: `_puzzle_out` hoje acessa `p.game`/`p.position` sem checar; passar a montar `game`/`mistake`/`ply` só quando `p.position is not None`.
- [ ] **Step 3: Commit** — `feat(fontes): PuzzleOut com fonte e último lance, guardar/tirar da repetição e salvar tática`.

---

### Task 3: Parser de estudos do Lichess

**Files:**
- Create: `backend/chess_trainer/core/studies/__init__.py`, `backend/chess_trainer/core/studies/parser.py`
- Test: `backend/tests/test_study_parser.py`

**Interfaces:**
- `parse_study_pgn(text: str) -> ParsedStudy` com `ParsedStudy(title: str, author: str, lichess_id: str | None, chapters: list[ParsedChapter])` e `ParsedChapter(order, name, lichess_url, fen, orientation, mode ("gamebook"|"read"), pgn (texto do capítulo), intro_comment, solution: dict | None, skipped_reason: str | None)`.
- Regras: um "jogo" PGN por capítulo (`chess.pgn.read_game` em loop); `title` = `[StudyName]` (ou o prefixo antes de ": " no `[Event]`), `author` = `[Annotator]` sem `https://lichess.org/@/`; `lichess_id` = trecho de `[ChapterURL]` (`/study/<id>/<chap>`); `name` = `[ChapterName]` (ou o `[Event]` após ": "); `fen` = `[FEN]` ou a inicial; `orientation` = `[Orientation]` se presente, senão lado a mover; `mode` = `gamebook` se `[ChapterMode] == "gamebook"`, senão `read`.
- Solução (só `gamebook`): solver = lado a mover na FEN; percorre a linha principal (`game.mainline()`), cada nó vira `{"uci", "by": "solver"|"engine" (alternando a partir de solver), "alternatives": []}`; `comments[str(i)]` = comentário do nó (sem os `[%cal …]`/`[%csl …]`/`[%eval …]`/`[%clk …]`, texto limpo com `strip()`), quando não vazio; `shapes[str(i)]` = `node.arrows()` → `{"orig","dest","brush"}` (mapa de cor: `G→green, R→red, B→blue, Y→yellow`) e casas de `%csl` → `{"orig","brush"}`; `intro` = comentário do nó raiz (`game.comment`) limpo; `shapes["0"]` = setas do nó raiz. `wrong_moves`: para cada nó da linha principal onde `by == "solver"`, cada variação (`node.parent.variations[1:]`) com comentário não vazio → `{uci_da_variação: comentário limpo}`. Sem lances → `mode = read`, `solution = None`. Lance ilegal (`ValueError`/`chess.IllegalMoveError` ao reproduzir) → `skipped_reason` e `solution = None`.
- Helper `clean_comment(text) -> str` que remove os comandos `[%…]`.

- [ ] **Step 1: Testes (falham)** — com a fixture real: `len(chapters) == 27`; contagem de `gamebook` vs `read` (calcular no teste lendo os headers com regex e comparar); capítulo 1 (`Pt2y3ild`): `fen` termina em `b kq - 2 10`, solver pretas, `moves[0].uci == "d8b6"`, `moves` = `d8b6, h1... ` (conferir: `10... Qb6+ 11. Kh1 Qxb5` → `d8b6, g1h1, b5... `— use os UCIs reais calculados no teste com python-chess a partir do SAN), `comments["0"]` contém "alinhamento", `intro` contém "acabaram de rocar", `wrong_moves` tem `e8g8` ("Assim seguiu a partida") e não tem `f5g6` (sem comentário); um capítulo com `%cal` produz `shapes` com `brush` certo; `title == "#PL05A - O jeito certo para achar tática em toda partida"`, `author == "basso01"`, `lichess_id == "4JKVAfaE"`. Casos sintéticos: PGN com lance ilegal → `skipped_reason`; PGN sem `[ChapterMode]` → `read`.
- [ ] **Step 2: Implementar** com `chess.pgn` (usar `node.arrows()` para `%cal`/`%csl`; `chess.pgn.Arrow` tem `tail`, `head`, `color`; casas são setas com `tail == head`).
- [ ] **Step 3: Commit** — `feat(estudos): parser de PGN de estudos do Lichess em capítulos e exercícios`.

---

### Task 4: Serviço e rotas de estudos

**Files:**
- Create: `backend/chess_trainer/core/studies/service.py`, `backend/chess_trainer/api/routes/studies.py`
- Modify: `backend/chess_trainer/api/schemas.py`, `backend/chess_trainer/api/app.py`
- Test: `backend/tests/test_study_service.py`, `backend/tests/test_api_studies.py`

**Interfaces:**
- `service.upsert_study(db, parsed: ParsedStudy, source_url: str | None, now) -> Study`: cria/atualiza o `Study` (chave `lichess_id`, senão `source_url`, senão novo); para cada capítulo, chave `lichess_url` (sem URL: `order` dentro do estudo): cria/atualiza `StudyChapter`; se `solution` existe: cria `Puzzle(source="study", kind="punish", category="study", theme="study", fen_start=fen, side_to_move, solution, end_reason="material_gain" ou "mate" (último lance dá mate?), solver_moves, chapter_id, in_queue=chapter.in_queue)` ou atualiza o existente (`fen_start`/`solution`/`solver_moves`; mantém id/SRS); capítulos ausentes na nova versão → `in_queue=False` no capítulo e no puzzle. Devolve o estudo. Relatório: `ImportReport(created, updated, skipped: list[str])` como segundo retorno.
- `service.fetch_study_pgn(lichess_id, http: httpx.Client | None) -> str`: `GET https://lichess.org/api/study/{id}.pgn`; 404 → `StudyNotFound`.
- `service.parse_lichess_url(url) -> str | None` (aceita `/study/<id>`, `/study/<id>/<chap>`, com ou sem `https://lichess.org`).
- `service.set_study_queue(db, study, in_queue)`, `service.delete_study(db, study)` (apaga reviews dos puzzles do estudo, puzzles, capítulos, estudo).
- Rotas (`api/routes/studies.py`, prefixo `/api`): `GET /studies` → `list[StudyOut]` (`id, title, author, source_url, lichess_id, imported_at, chapters, in_queue (capítulos na fila), due_today`); `GET /studies/{id}` → `StudyDetail` (+ `chapters: list[ChapterOut(id, order, name, lichess_url, mode, in_queue, puzzle_id, intro_comment)]`); `POST /studies/import {url?: str, pgn?: str}` → 202 job `import_study` (URL inválida → 400; ambos vazios → 400); `POST /studies/{id}/reimport` → 202 (precisa de `lichess_id`; senão 400); `POST /studies/{id}/queue {in_queue}` → `StudyOut`; `DELETE /studies/{id}` → 204. Job: baixa (ou usa o `pgn` do corpo), `parse_study_pgn`, `upsert_study`, `progress("import_study", n, total, "N capítulos, M exercícios, K pulados")`; `StudyNotFound` → job em erro com a mensagem "estudo privado ou inexistente; exporte o PGN no Lichess e cole aqui". `app.state.study_http` (factory opcional para testes; padrão `httpx.Client(follow_redirects=True, timeout=30)`).
- `create_app(..., study_http_factory=None)`.

- [ ] **Step 1: Testes (falham)** — `test_study_service.py`: upsert com a fixture cria 27 capítulos e N puzzles `study` na fila; reimport com o mesmo PGN não duplica; PGN modificado (remover o último capítulo e trocar a linha do primeiro) → capítulo removido `in_queue=False`, puzzle do primeiro com `solution` nova e mesmo id; `delete_study` apaga tudo e não toca em puzzles `own`. `test_api_studies.py`: `POST /studies/import {url:"https://lichess.org/study/4JKVAfaE"}` com `study_http_factory` de `MockTransport` que devolve a fixture → job idle, `GET /studies` lista 1 com `chapters == 27`; `GET /queue?study_id=` lista os puzzles; `{url: "lixo"}` → 400; mock 404 → job `error` com a mensagem; `{pgn: <fixture>}` importa sem rede; `POST /studies/{id}/queue {in_queue:false}` zera `in_queue`; `DELETE` → 204 e lista vazia.
- [ ] **Step 2: Implementar.** Incluir o router em `app.py`. `JobCard` do frontend conhecerá `import_study` na Task 7.
- [ ] **Step 3: Commit** — `feat(estudos): importação de estudos do Lichess por URL ou PGN, reimport, fila e remoção`.

---

### Task 5: Frontend — tipos, fontes na sessão, guardar/tirar, comentários do autor

**Files:**
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/train/usePuzzle.ts`, `frontend/src/train/PuzzleView.tsx`, `frontend/src/train/ResultPanel.tsx`, `frontend/src/train/TacticResultPanel.tsx`, `frontend/src/train/SessionStart.tsx`, `frontend/src/train/TrainPage.tsx`, `frontend/src/train/SessionSummary.tsx`, `frontend/src/pages/MistakesPage.tsx`, `frontend/src/lib/format.ts`
- Create: `frontend/src/train/QueueButtons.tsx`
- Test: `frontend/tests/` (novos: `queueButtons.test.tsx`, `sessionStartSources.test.tsx`; ajustar `puzzleView`, `session`, `tacticSession`)

**Interfaces:**
- Types: `PuzzleOut.source: "own"|"lichess"|"study"`, `in_queue`, `fen_before: string|null`, `last_move: string|null`, `study: StudyRef|null`, `game: GameRef|null`, `mistake: MistakeRef|null`, `ply: number|null`, `move_played: string|null`; `Solution` ganha `wrong_moves?`, `comments?`, `shapes?`, `intro?`; `TacticOut.saved`; `QueueFilters.sources?: string[]`, `study_id?`; `DashboardOut.by_source`; `PuzzleRef.in_queue`; `StudyOut`, `StudyDetail`, `ChapterOut`.
- Client: `setQueue(id, in_queue)`, `saveTactic(lichessId)`, `studies()`, `study(id)`, `importStudy({url}|{pgn})`, `reimportStudy(id)`, `setStudyQueue(id, in_queue)`, `deleteStudy(id)`; `queue()` serializa `sources` como `a,b`.
- Queries: `useStudies`, `useStudy(id)`, mutations `useSetQueue`, `useSaveTactic`, `useImportStudy` (via `useStartJob` kind `import_study` com payload), `useStudyActions`; invalidar `["queue"]`, `["dashboard"]`, `["studies"]`, `["puzzle"]`.
- `usePuzzle`: ao errar, se `solution.wrong_moves?.[uci]` existe, a mensagem de erro é o comentário do autor (`tone: "bad"`); ao acertar um lance com `comments[idx]`, a mensagem "Certo!" vira `Certo! — <comentário>`.
- `QueueButtons({ puzzle })`: para `PuzzleOut`: "Tirar da repetição" / "Voltar para a repetição" (mutation, estado otimista simples); para `TacticOut`: "Guardar para repetir" / "Guardado ✓" (desabilitado quando salvo).
- `PuzzleView`: cabeçalho por fonte — `own` como hoje; `lichess`: "tática do Lichess guardada · rating?" (sem rating: só tema); `study`: "Estudo · Capítulo" + enunciado (`solution.intro`) em destaque. `ResultPanel`: links "partida no chess.com/app" só com `game`; para `study`, link "ver no Lichess" (capítulo) e comentários do autor exibidos sob a linha navegável na posição corrente (`comments[pos-1]`); `QueueButtons` em ambos os painéis de resultado.
- `SessionStart`: fonte "Meus erros" vira chips de fontes (`own`, `lichess`, `study`, multi; vazio = todas) + select de estudo (via `useStudies`) quando `study` está marcado; `?study=<id>` na URL pré-marca `study` e o estudo; persistir `train.sources`. Os selects de tipo/cor/categoria continuam (aplicam a `own`).
- `SessionSummary`: linha dos errados usa `game` quando existe, senão "Estudo · Capítulo" ou "tática do Lichess".
- `MistakesPage`: etiqueta "fora da repetição" quando `puzzle.in_queue === false`.

- [ ] **Step 1: Testes (falham)**; **Step 2: Implementar**; **Step 3: `npm test -- --run`, `tsc`, `build`**; **Step 4: Commit** — `feat(fontes): fontes na sessão, guardar/tirar da repetição e comentários do autor`.

---

### Task 6: Frontend — último lance animado e marcações

**Files:**
- Modify: `frontend/src/board/Board.tsx`, `frontend/src/train/usePuzzle.ts`, `frontend/src/train/PuzzleView.tsx`, `frontend/src/train/LineViewer.tsx`, `frontend/src/train/ResultPanel.tsx`, `frontend/src/train/TacticResultPanel.tsx`, `frontend/src/analysis/AnalysisBoard.tsx`, `frontend/src/styles/base.css` (se preciso para as cores das setas)
- Test: `frontend/tests/usePuzzle.test.ts` (append), `frontend/tests/lineViewer.test.tsx` (append), `frontend/tests/board.test.tsx` (create)

**Interfaces:**
- `Board` ganha `drawable?: boolean` (padrão `false`) → `drawable: { enabled: true, visible: true, eraseOnClick: true, shapes: [] }`; `autoShapes` continua para dica/setas da engine/setas do autor. Ao mudar `fen`, as marcações do usuário são limpas (`cg.setShapes([])`) — regra do spec (não persistem).
- `usePuzzle`: novo `phase: "intro"` quando `puzzle.fen_before && puzzle.last_move`: estado inicial `fen = fen_before`, `turn` do adversário, sem `dests`; após `opts.introDelayMs ?? 400` aplica `last_move` via chess.js num tabuleiro auxiliar (ou simplesmente troca para `fen_start` com `lastMove` = [from, to] — chessground anima a diferença), `phase = "awaiting_move"`, `startedAt = now()` só aqui. `PuzzleInput` ganha `fen_before?: string | null`, `last_move?: string | null`. Sem último lance, comportamento atual. Testes: com `fen_before`, fase inicial `intro`, `tryMove` ignorado, após o timer fase `awaiting_move` e `fen === fen_start`; duração enviada no submit não inclui a introdução (usar `now` injetado).
- `PuzzleView`: `drawable`; `arrows`/`highlight` do autor na posição inicial (`solution.shapes?.["0"]`) enquanto `state.idx === 0`.
- `LineViewer`: prop `fenBefore?: string` + `lastMoveUci?: string` → quando presentes, a linha começa em `fenBefore` com o último lance como posição 0 e `startPly` recua 1 (numeração correta); prop `shapes?: Record<string, Shape[]>` → `autoShapes` da posição corrente; prop `drawable` (padrão `true`); `initialPos` ajustado pelos chamadores (+1).
- `AnalysisBoard`: `drawable`.

- [ ] **Step 1: Testes (falham)**; **Step 2: Implementar**; **Step 3: verificar**; **Step 4: Commit** — `feat(tabuleiro): último lance do adversário animado e marcações com o botão direito`.

---

### Task 7: Frontend — tela Estudos, menu, painel por fonte, docs

**Files:**
- Create: `frontend/src/pages/StudiesPage.tsx`, `frontend/src/pages/StudyDetailPage.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/Nav.tsx`, `frontend/src/components/JobCard.tsx`, `frontend/src/pages/DashboardPage.tsx`, `README.md`, `backend/README.md`
- Test: `frontend/tests/studiesPage.test.tsx`, `frontend/tests/studyDetailPage.test.tsx`, `frontend/tests/dashboardPage.test.tsx` (append)

**Interfaces:**
- Rotas `/estudos` e `/estudos/:id`; item "Estudos" no menu (ícone "📚" ou "▤").
- `StudiesPage`: lista (título, autor, capítulos, na fila, vencidos hoje), ações (Treinar este estudo → `/treinar?study=<id>`; Reimportar; Tirar/Voltar; Remover com `Modal` de confirmação); formulário "Importar do Lichess" (URL) com alternância "colar PGN" (textarea); mostra o `JobCard` para acompanhar.
- `StudyDetailPage`: capítulos em ordem com modo, "Treinar este" (`/treinar?puzzle=<puzzle_id>`), "ver no Lichess", enunciado; capítulos `read` com etiqueta "leitura (sem exercício)".
- `JobCard`: `import_study: "Importação de estudo do Lichess"`.
- `DashboardPage`: no cartão Estado, "N dos seus erros · N do Lichess · N de estudos" a partir de `by_source`.
- README: seção "Estudos do Lichess" e "Fontes de exercício"; backend README: rotas novas e `study_http_factory`.

- [ ] **Step 1: Testes (falham)**; **Step 2: Implementar**; **Step 3: verificar**; **Step 4: Commit** — `feat(estudos): tela Estudos com importação, treino por estudo e painel por fonte`.

---

## Self-review

- Spec §2 → T1/T2; §3 → T1/T2/T5; §4 → T6; §5 → T3/T4/T7; §6 → T2/T4; §7 → T5/T7; §8 → testes por task.
- Nomes: `source`, `in_queue`, `external_id`, `chapter_id`, `fen_before`, `last_move`; `sources`/`study_id`; `parse_study_pgn`, `upsert_study`, `fetch_study_pgn`, `parse_lichess_url`, `set_study_queue`, `delete_study`; rotas `/studies…`, `/puzzles/{id}/queue`, `/tactics/{id}/save`; job `import_study`; frontend `QueueButtons`, `useStudies`, `useStudy`, fase `intro`.
- Decisão: `intro` dentro de `solution` (sem coluna nova em `puzzles`); `kind="punish"` para fontes externas.
