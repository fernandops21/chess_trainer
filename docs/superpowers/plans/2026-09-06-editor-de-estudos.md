# Editor de estudos (ciclo B2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar e editar estudos e capítulos no app com um tabuleiro de análise completo (árvore de variações, comentários, marcações salvas, engine), gerando o exercício de repetição de cada capítulo e exportando PGN compatível com o Lichess.

**Architecture:** A árvore de lances (JSON, ver Global Constraints) é a fonte da verdade do capítulo (`StudyChapter.tree_json`); o backend converte árvore ⇄ `chess.pgn.Game` (`core/studies/tree.py`), valida, gera o PGN e o exercício (reusando o gerador de solução do parser do B1). No frontend, `useMoveTree` mantém a árvore em memória; `AnalysisBoard` é reescrito sobre ele e serve tanto para `/analise` quanto para o editor de capítulo (`editable`), com "Salvar como capítulo" em qualquer análise.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 + SQLite, python-chess (`chess.pgn`); React 19 + TS, chessground (drawable), chess.js, TanStack Query, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-06-editor-de-estudos-design.md`

## Global Constraints

- Português do Brasil na interface; nunca "regerar/regeração".
- Árvore (JSON): `{"fen": str, "orientation": "white"|"black", "intro": str, "root": {"children": [node…]}}`, `node = {"id": str, "uci": str, "san": str, "comment": str, "shapes": [{"orig","dest"?,"brush"}], "nags": [int], "children": [node…]}`. Primeiro filho = linha principal. `id` gerado no cliente (`n` + contador), estável dentro do capítulo. Limites: 2 000 nós, comentário ≤ 4 000 caracteres.
- Marcações: `brush` ∈ `green|red|blue|yellow`; no PGN viram `[%cal Ge2e4,…]`/`[%csl Rd5,…]` no comentário do nó (as do nó raiz, no comentário inicial).
- Regeneração do exercício ao salvar mantém `Puzzle.id` e SRS quando `fen_start` e a linha principal (lista de UCIs) não mudam; se mudarem, atualiza no lugar (mesma regra do reimport do B1). `mode = read` → sem exercício (puzzle existente fica `in_queue = false`).
- Nada apaga dados do usuário além do que a ação pede (apagar capítulo apaga seu puzzle e revisões, com confirmação na UI).
- Backend `uv run pytest -q` e frontend `npm test -- --run` + `npx tsc --noEmit -p .` + `npm run build` verdes ao fim de cada task. Testes frontend só em `frontend/tests/**`.
- Commits em português, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, `git commit -F` com arquivo UTF-8 em `.superpowers/`.

---

### Task 1: Árvore ⇄ PGN no backend, colunas novas, parser devolve a árvore

**Files:**
- Create: `backend/chess_trainer/core/studies/tree.py`
- Modify: `backend/chess_trainer/core/models.py` (`Study.origin`, `Study.updated_at`, `StudyChapter.tree_json`, `StudyChapter.updated_at`), `backend/chess_trainer/core/db.py` (colunas novas em `studies`/`study_chapters` no `migrate`, só ADD COLUMN), `backend/chess_trainer/core/studies/parser.py` (`ParsedChapter.tree`, expor `solution_from_game(game) -> dict | None`), `backend/chess_trainer/core/studies/service.py` (gravar `tree_json`, `origin="lichess"`)
- Test: `backend/tests/test_study_tree.py`, `backend/tests/test_study_parser.py` (append), `backend/tests/test_migration.py` (append)

**Interfaces:**
- `game_to_tree(game: chess.pgn.Game) -> dict` (ids `n1…` em pré-ordem; `san` via `board.san`; `nags` = `sorted(node.nags)`; `shapes` de `node.arrows()`; `comment` limpo de `[%…]`; `intro` = comentário limpo da raiz; `fen` = `game.board().fen()` (ou a inicial); `orientation` do header ou lado a mover).
- `tree_to_game(tree: dict, headers: dict[str, str]) -> chess.pgn.Game` (aplica `[FEN]`/`[SetUp]` quando `fen` ≠ inicial; escreve comentários com `[%cal]`/`[%csl]` recompostos; NAGs; variações).
- `validate_tree(tree: dict) -> list[str]` (erros legíveis: FEN inválida, lance ilegal em `<san>` do nó `<id>`, nós > 2000, comentário > 4000, `brush` desconhecido); lista vazia = ok.
- `solution_from_tree(tree: dict) -> dict | None` = `parser.solution_from_game(tree_to_game(tree, {}))`.
- `chapter_pgn(chapter: StudyChapter, study: Study) -> str` com headers `Event "<título>: <capítulo>"`, `Site "chess-trainer"`, `Result "*"`, `StudyName`, `ChapterName`, `ChapterMode "gamebook"` se aplicável, `Orientation`, `FEN`/`SetUp`; `study_pgn(study) -> str` = capítulos em ordem separados por linha em branco.
- Migração: `ALTER TABLE studies ADD COLUMN origin VARCHAR(8) DEFAULT 'lichess'`, `updated_at DATETIME`, `ALTER TABLE study_chapters ADD COLUMN tree_json TEXT`, `updated_at DATETIME` (só quando ausentes; sem rebuild). Capítulos importados antes do B2 sem `tree_json`: o serviço preenche na próxima leitura (`ensure_tree(chapter)` faz `game_to_tree(read_game(chapter.pgn))` e grava).

- [ ] **Step 1: Testes (falham)** — round trip com a fixture real: para cada capítulo, `tree = game_to_tree(game)`; `game2 = tree_to_game(tree, headers)`; `game_to_tree(game2) == tree`; a linha principal e as variações batem com o PGN original (comparar `str(game.mainline_moves())`); um capítulo com `%cal` mantém as setas após o round trip; `validate_tree` acusa lance ilegal, FEN inválida, > 2000 nós; `solution_from_tree` do capítulo 1 == `solution` do parser do B1; `chapter_pgn` contém `[ChapterMode "gamebook"]` e `[FEN …]`; migração adiciona as colunas num banco com o esquema do B1.
- [ ] **Step 2: Implementar**; refatorar o parser para que `_solution` vire `solution_from_game` público e `_chapter` preencha `tree`.
- [ ] **Step 3: Commit** — `feat(estudos): árvore de lances em JSON, conversão para PGN e validação`.

---

### Task 2: Rotas de criação/edição/exportação de estudos

**Files:**
- Modify: `backend/chess_trainer/core/studies/service.py`, `backend/chess_trainer/api/routes/studies.py`, `backend/chess_trainer/api/schemas.py`
- Test: `backend/tests/test_api_studies.py` (append), `backend/tests/test_study_service.py` (append)

**Interfaces:**
- Serviço: `create_study(db, title, author) -> Study` (`origin="local"`), `update_study(db, study, title, author, chapter_order: list[str] | None)`, `create_chapter(db, study, name, fen, orientation, mode) -> StudyChapter` (árvore vazia com `fen`), `save_chapter(db, chapter, name, mode, orientation, tree) -> StudyChapter` (valida → `tree_json`, `pgn = chapter_pgn`, `intro_comment = tree["intro"]`, `fen`, e regenera o puzzle: `solution_from_tree` → cria/atualiza/desliga conforme Global Constraints), `delete_chapter(db, chapter)` (puzzle + revisões + capítulo; reordena os demais), `duplicate_chapter(db, chapter) -> StudyChapter`, `chapter_detail(chapter) -> dict` (inclui `tree` garantido por `ensure_tree`).
- Rotas: `POST /api/studies {title, author}` → 201 `StudyOut`; `PUT /api/studies/{id} {title?, author?, chapter_order?}` → `StudyOut`; `GET /api/studies/{id}/chapters/{cid}` → `ChapterDetail` (`ChapterOut` + `fen`, `orientation`, `tree`, `pgn`); `POST /api/studies/{id}/chapters {name, fen?, orientation?, mode?}` → 201 `ChapterDetail`; `PUT /api/studies/{id}/chapters/{cid} {name, mode, orientation, tree}` → `ChapterDetail` (422 com a lista de erros de `validate_tree`); `DELETE …/chapters/{cid}` → 204; `POST …/chapters/{cid}/duplicate` → 201; `GET /api/studies/{id}/pgn` e `GET …/chapters/{cid}/pgn` → `text/plain; charset=utf-8` com `Content-Disposition: attachment; filename="<slug>.pgn"`.
- `StudyOut` ganha `origin`, `updated_at`; `ChapterOut` ganha `updated_at`.

- [ ] **Step 1: Testes (falham)** — criar estudo local, capítulo, salvar árvore (com variação comentada e seta) → puzzle criado com `wrong_moves`/`shapes`; salvar de novo com o mesmo mainline → mesmo `puzzle.id` e SRS intactos após uma `Review`; mudar mainline → mesmo id, solução nova; `mode=read` → puzzle `in_queue=false`; árvore ilegal → 422 com mensagem; duplicar; apagar (puzzle e revisões somem; outros intactos); reordenar; exportar estudo local e reimportar via `POST /studies/import {pgn}` → mesmas árvores (round trip de ponta a ponta); exportar o estudo importado real → reimportar → mesmas árvores; `GET /studies/{id}/chapters/{cid}` de um capítulo importado antes do B2 (sem `tree_json`) devolve `tree` preenchido.
- [ ] **Step 2: Implementar**; **Step 3: Commit** — `feat(estudos): criação, edição, exportação e duplicação de estudos e capítulos`.

---

### Task 3: Frontend — `useMoveTree`

**Files:**
- Create: `frontend/src/analysis/moveTree.ts` (tipos + funções puras), `frontend/src/analysis/useMoveTree.ts`
- Test: `frontend/tests/moveTree.test.ts`

**Interfaces:**
- Tipos: `Shape {orig; dest?; brush}`, `TreeNode {id; uci; san; comment; shapes; nags; children}`, `Tree {fen; orientation; intro; root: {children}}`.
- Funções puras (`moveTree.ts`): `emptyTree(fen, orientation)`, `findNode(tree, id)`, `pathTo(tree, id) -> TreeNode[]`, `fenAt(tree, id)` (chess.js, memoizável), `mainline(tree) -> TreeNode[]`, `addMove(tree, parentId | null, uci) -> {tree, node, created}` (segue filho existente com o mesmo `uci`), `promote(tree, id)` (move o nó para a primeira posição entre os irmãos, recursivamente até a raiz — "promover a linha principal"), `deleteFrom(tree, id)`, `setComment/setShapes/setNags(tree, id, …)`, `nextId(tree)`, `countNodes(tree)`, `insertLine(tree, parentId, ucis[])`.
- Hook `useMoveTree(initial: Tree)`: `{ tree, currentId, fen, turn, lastMove, dests, path, play(uci), goTo(id), goStart(), prev(), next(), up(), down() (irmão anterior/seguinte), promote(), deleteFrom(), setComment(text), setShapes(shapes), toggleNag(n), insertLine(ucis), setTree(tree), dirty, markSaved() }`. `dirty` vira `true` em qualquer mutação e `false` em `markSaved`/`setTree`.

- [ ] **Step 1: Testes (falham)** — `addMove` cria variação quando o lance difere e segue o filho quando igual; `promote` de uma variação aninhada torna-a linha principal em todos os níveis; `deleteFrom` remove a subárvore; `fenAt` correto após promoção; `mainline` após promoção; `insertLine` com lance ilegal para no primeiro ilegal e devolve quantos entraram; hook: `play` avança `currentId`, `prev/next/up/down`, `dirty`.
- [ ] **Step 2: Implementar**; **Step 3: Commit** — `feat(analise): árvore de lances com variações, comentários e marcações`.

---

### Task 4: Frontend — tabuleiro de análise completo (`/analise`) sobre a árvore

**Files:**
- Modify: `frontend/src/analysis/AnalysisBoard.tsx`, `frontend/src/analysis/useAnalysis.ts` (remover ou reduzir a um adaptador; preferir remover e atualizar os testes), `frontend/src/pages/AnalysisPage.tsx`, `frontend/src/components/Nav.tsx`, `frontend/src/api/{types,client,queries}.ts`, `frontend/src/styles/base.css`
- Create: `frontend/src/analysis/MoveTreeView.tsx`, `frontend/src/analysis/NodeMenu.tsx`, `frontend/src/analysis/SaveChapterModal.tsx`
- Test: `frontend/tests/analysisBoard.test.tsx` (reescrever `useAnalysis.test.ts`), `frontend/tests/moveTreeView.test.tsx`, `frontend/tests/saveChapterModal.test.tsx`

**Interfaces:**
- `AnalysisBoard({ tree: Tree, editable?: boolean, onTreeChange?: (t: Tree) => void, backTo?: string, showSaveAsChapter?: boolean })` — `editable` liga comentários/NAGs/marcações salvas/menu do nó; sem `editable`, a árvore é navegável e ainda é possível jogar lances (exploração temporária) mas não editar comentários.
- `MoveTreeView({ tree, currentId, onGoTo, onContextMenu })`: linha principal corrida (`1. e4 e5 2. Nf3`), variações entre parênteses recuadas, NAG como sufixo (`!`, `?`, `!!`, `??`, `!?`, `?!`), comentário em itálico após o lance (truncado a 80 caracteres na árvore; completo na caixa), nó atual destacado; clique = `goTo`; botão direito = menu.
- `NodeMenu`: "Promover a linha principal", "Apagar daqui", NAG toggles.
- Engine: reusar `useAnalyse(fen)`; linhas clicáveis (`insertLine` no nó atual) e "adicionar como variação".
- Teclado: ← → (prev/next), ↑ ↓ (up/down), Home (início); Ctrl+S dispara `onSave` quando existir.
- `SaveChapterModal({ tree, onClose })`: escolher estudo existente (`useStudies`, só `origin === "local"` ou qualquer? → qualquer; estudos importados são editáveis) ou "Novo estudo" (título); nome do capítulo; modo; chama `POST /studies` (se novo) + `POST /studies/{id}/chapters` + `PUT …/chapters/{cid}` com a árvore; navega para o editor do capítulo.
- `AnalysisPage`: sem `?fen=` abre na posição inicial; item "Análise" no menu; mostra "Salvar como capítulo".
- Client: `createStudy`, `updateStudy`, `chapter(id, cid)`, `createChapter`, `saveChapter`, `deleteChapter`, `duplicateChapter`, `studyPgnUrl(id)`, `chapterPgnUrl(id, cid)`; queries `useChapter`, mutations.

- [ ] **Step 1: Testes (falham)**; **Step 2: Implementar**; **Step 3: verificar**; **Step 4: Commit** — `feat(analise): tabuleiro de análise com árvore de variações, engine e salvar como capítulo`.

---

### Task 5: Frontend — editor de capítulo, edição do estudo e leitura

**Files:**
- Create: `frontend/src/pages/ChapterEditorPage.tsx`, `frontend/src/pages/ChapterViewPage.tsx`, `frontend/src/studies/StudyEditor.tsx`
- Modify: `frontend/src/pages/StudiesPage.tsx`, `frontend/src/pages/StudyDetailPage.tsx`, `frontend/src/App.tsx`, `frontend/src/api/*`
- Test: `frontend/tests/chapterEditorPage.test.tsx`, `frontend/tests/studyDetailPage.test.tsx` (append)

**Interfaces:**
- Rotas: `/estudos/:id/capitulos/:cid/editar` (editor), `/estudos/:id/capitulos/:cid` (leitura). `StudyDetailPage`: "Editar" em cada capítulo, "Novo capítulo" (modal: nome, posição inicial: padrão / FEN colada / a partir da partida — campo de id de partida e ply; modo), "Duplicar", "Apagar" (confirmação), reordenar (botões ↑↓, chamando `PUT /studies/{id}` com `chapter_order`), "Exportar PGN" (estudo e capítulo, links `download`), edição do título/autor inline; aviso quando o estudo é importado ("reimportar sobrescreve as edições").
- `ChapterEditorPage`: cabeçalho (nome, modo, orientação, enunciado `intro`), `AnalysisBoard editable` com a árvore do capítulo, "Salvar" (e Ctrl+S) → `PUT …/chapters/{cid}`; erros 422 mostrados; `beforeunload` + bloqueio de navegação (`useBlocker`) quando `dirty`.
- `ChapterViewPage`: `AnalysisBoard` não editável com a árvore, comentários e marcações do autor; botão "Treinar este" quando há puzzle; "Editar".
- `StudiesPage`: "Novo estudo" (título) → cria e abre o detalhe.
- Fluxo "a partir da partida": no `GameDetailPage`, o botão "Explorar daqui" já abre `/analise?fen=`; "Salvar como capítulo" cobre o caso.

- [ ] **Step 1: Testes (falham)**; **Step 2: Implementar**; **Step 3: verificar**; **Step 4: Commit** — `feat(estudos): editor de capítulo, edição do estudo, leitura e exportação`.

---

### Task 6: Docs e pendências

- README: "Criar estudos aqui" (fluxo, exportar/importar no Lichess), atalhos do editor; backend README: rotas novas; `docs/superpowers/plans/2026-09-06-editor-de-estudos-followups.md`.
- Commit — `docs(estudos): editor de estudos e exportação PGN`.

## Self-review

- Spec §2 → T1; §3 → T3/T4/T5; §4 → T1/T2; §5 → T2; §6 → testes por task; §7 fora.
- Nomes: `game_to_tree`, `tree_to_game`, `validate_tree`, `solution_from_tree`, `solution_from_game`, `chapter_pgn`, `study_pgn`, `ensure_tree`, `save_chapter`, `create_chapter`, `duplicate_chapter`, `delete_chapter`; frontend `useMoveTree`, `MoveTreeView`, `NodeMenu`, `SaveChapterModal`, `ChapterEditorPage`, `ChapterViewPage`.
