# Dica em estágios, montar posição e livro de aberturas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) dica sem limite em dois estágios (mostrar peça → jogar o lance) em todos os puzzles; (2) "Montar posição" no tabuleiro de análise e no editor de capítulo; (3) livro de aberturas (explorador do Lichess: mestres e jogadores) como painel da Análise, via proxy no backend com token pessoal do Lichess.

**Spec (aprovado em conversa, 2026-09-07):**
1. Dica: primeiro clique destaca a peça; segundo clique no mesmo lance joga o lance por você (a engine responde); a cada lance seu o botão volta ao primeiro estágio; sem limite até o fim. Rótulos: "Dica" → "Mostrar peça" (após 1º clique vira) "Jogar o lance". Qualquer dica conta como erro (como hoje). Vale em erros, táticas e estudos.
2. Montar posição: botão "Montar posição" no `AnalysisBoard` (modo editável e não editável) e no modal "Novo capítulo" (terceira opção). Modo de montagem: paleta com as 12 peças + "apagar"; clicar na paleta seleciona a peça e clicar em casas coloca (clique de novo na mesma peça da paleta desmarca); arrastar peças no tabuleiro livremente (`movable.free`); "apagar" selecionado + clique remove. Controles: lado a jogar, roques (4 caixas, habilitadas só quando rei/torre estão nas casas certas), "Posição inicial", "Limpar", "Inverter", campo FEN editável nos dois sentidos. Validação (chess.js): um rei de cada cor, rei do lado que não joga fora de xeque, peões fora da 1ª/8ª fileira, ≤ 16 peças por lado; erros listados. "Usar posição" zera a árvore com a nova FEN (confirmação se havia lances) e a engine avalia dali. "Cancelar" volta sem mudar nada.
3. Livro de aberturas: painel "Aberturas" ao lado da engine na Análise (aba ou seção), por posição: base de mestres ou de jogadores do Lichess (seletor; jogadores com ritmos rapid+classical e ratings 1600–2500 por padrão), tabela com lance (SAN), nº de partidas, % brancas/empates/pretas em barra, clique joga o lance (como as linhas da engine); nome da abertura quando a API devolve; "sem partidas nesta posição" quando vazio. Backend `GET /api/openings?fen=&db=masters|lichess` faz proxy para `https://explorer.lichess.ovh/{masters|lichess}` com `Authorization: Bearer <token>` (Setting `lichess_token`, novo campo em Configurações, tipo password, com link para criar o token em https://lichess.org/account/oauth/token, sem escopos), cache em memória (LRU 500 por fen+db, TTL 24 h), 401/403 → 400 com mensagem "configure o token do Lichess em Configurações"; 429 → 503 "limite do Lichess; tente em instantes"; sem token → 400 com a mesma orientação (o painel mostra o aviso em vez da tabela). Sem rede em testes (MockTransport). O token nunca aparece nas respostas da API (`SettingsOut` devolve `lichess_token_set: bool`, não o valor; `PUT` aceita `lichess_token`; string vazia apaga).

## Global Constraints

- Português do Brasil; nunca "regerar/regeração".
- Backend `uv run pytest -q` (399 hoje) e frontend `npx vitest run` (243), `npx tsc --noEmit -p .`, `npm run build` verdes ao fim de cada task. Testes frontend só em `frontend/tests/**`.
- `usePuzzle`: contrato de uma instância por puzzle. Dica sempre `used_hint = true` no submit.
- O token do Lichess é dado pelo usuário na interface; nunca é logado, nunca sai em respostas, nunca vai para o git.
- Commits em português, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, via `git commit -F` com arquivo UTF-8 em `.superpowers/`.

---

### Task 1: Dica em dois estágios, sem limite

**Files:** `frontend/src/train/usePuzzle.ts`, `frontend/src/train/PuzzleView.tsx`, `frontend/tests/usePuzzle.test.ts`, `frontend/tests/puzzleView.test.tsx`.

- `PuzzleState` ganha `hintStage: 0 | 1` (0 = nenhuma dica neste lance; 1 = peça destacada). `useHint()`: se `hintStage === 0` → `usedHint = true`, `hint = casa de origem`, `hintStage = 1`, mensagem "Peça destacada. Clique de novo para jogar o lance (dica conta como erro)."; se `hintStage === 1` → chama `applySolverMove(expected.uci)` (o lance esperado, com promoção se houver) e a máquina segue (engine responde, próximo lance libera com `hintStage = 0`). Ao aplicar qualquer lance do solver, `hintStage` volta a 0 e `hint` a `undefined`. O botão fica habilitado em `awaiting_move` sempre (sem `disabled={state.usedHint}`).
- `PuzzleView`: rótulo `state.hintStage === 1 ? "Jogar o lance" : "Mostrar peça"`; `aria-label="Dica"` mantido.
- Testes: dois cliques jogam o lance esperado e a engine responde; no lance seguinte a dica volta ao estágio 0 e pode ser usada de novo; `used_hint: true` no submit; puzzle com promoção na dica joga com a promoção certa.
- Commit: `feat(treino): dica em dois estágios e sem limite por puzzle`.

### Task 2: Montar posição

**Files:** create `frontend/src/analysis/PositionEditor.tsx`, `frontend/src/analysis/positionEditor.ts` (funções puras: `fenFromBoard`, `boardFromFen`, `validatePosition(fen) -> string[]`, `castlingAvailable(board) -> {K,Q,k,q}`), modify `frontend/src/analysis/AnalysisBoard.tsx` (botão "Montar posição" + troca de modo), `frontend/src/board/Board.tsx` (props `free?: boolean` → `movable.free`, `onSquareClick?`, `onDropOff?` para remover peça arrastada para fora se o chessground suportar via `draggable.deleteOnDropOff`), `frontend/src/studies/StudyEditor.tsx` (opção "Montar posição" no modal Novo capítulo abrindo o `PositionEditor` embutido), `frontend/src/styles/base.css` (paleta). Tests: `frontend/tests/positionEditor.test.ts(x)`.

- `PositionEditor({ initialFen, onUse(fen), onCancel })`: estado = peças por casa (Map), lado a jogar, roques; paleta (`button` por peça com `aria-pressed`), clique no tabuleiro (usar o `onSquareClick` do `Board` via chessground `events.select`), arrastar livre (`movable.free: true`, `movable.color: "both"`, `draggable.deleteOnDropOff: true`), FEN em `input` sincronizado (edição válida atualiza o tabuleiro; inválida mostra erro e não aplica), validação ao vivo, "Usar posição" desabilitado com erros.
- `AnalysisBoard`: prop/estado `montando`; ao "Usar posição": se a árvore tem lances → `window.confirm("Substituir a análise atual pela nova posição?")`; então `setTree(emptyTree(fen, orientation))` e `onTreeChange`.
- Modal Novo capítulo: opção "montar posição" mostra o `PositionEditor` dentro do modal (ou botão que abre em tela cheia); FEN resultante vai para o `createChapter`.
- Testes: funções puras (fen ida/volta, validação de cada regra, roques disponíveis); componente: clicar peça da paleta + casa coloca e a FEN muda; "Usar posição" chama `onUse` com a FEN; inválida desabilita.
- Commit: `feat(analise): montar posição no tabuleiro de análise e no novo capítulo`.

### Task 3: Livro de aberturas

**Files:** backend: create `backend/chess_trainer/core/openings.py` (`OpeningExplorer` com cache LRU/TTL, `fetch(fen, db, token, http) -> dict` normalizado: `{opening: {eco, name} | null, total, white, draws, black, moves: [{uci, san, games, white, draws, black, avg_rating?}]}`), `backend/chess_trainer/api/routes/openings.py` (`GET /api/openings?fen=&db=`), modify `config.py` (`lichess_token: str = ""`), `api/schemas.py` (`SettingsOut.lichess_token_set: bool` em vez do valor; `SettingsIn.lichess_token`), `api/routes/system.py` (mapear), `api/app.py` (router; `app.state.openings = OpeningExplorer(http_factory)`), tests `backend/tests/test_openings.py`, `tests/test_api_system.py` (append). Frontend: `frontend/src/api/{types,client,queries}.ts` (`useOpenings(fen, db)`), create `frontend/src/analysis/OpeningsPanel.tsx`, modify `AnalysisBoard.tsx` (abas "Engine" / "Aberturas" no painel lateral, ou seção abaixo), `pages/SettingsPage.tsx` (campo "Token do Lichess", `type="password"`, texto de ajuda com o link para criar o token e o aviso de que ele fica só no seu banco), tests `frontend/tests/openingsPanel.test.tsx`, `settingsPage.test.tsx` (append), `backend README`, `README`.

- Backend: URL `https://explorer.lichess.ovh/masters?fen=<fen>&topGames=0` e `https://explorer.lichess.ovh/lichess?variant=standard&speeds=rapid,classical&ratings=1600,1800,2000,2200,2500&fen=<fen>&topGames=0&recentGames=0`; cabeçalhos `Authorization: Bearer <token>`, `User-Agent: chess-trainer/0.1`, `Accept: application/json`; timeout 10 s; sem token → 400 `"configure o token do Lichess em Configurações"`; 401/403 → 400 `"token do Lichess recusado; gere outro em Configurações"`; 429 → 503; outros erros → 502. FEN validada com python-chess (400). Cache por (db, fen) TTL 24 h, 500 entradas.
- Frontend: `OpeningsPanel({ fen, onPlay(uci) })` com seletor mestres/jogadores (persistido `analysis.openingsDb`), tabela, barra de resultado (três segmentos coloridos com título acessível), nome da abertura, estados: carregando, sem token (mensagem + link para /config), sem partidas, erro.
- Testes: backend com MockTransport (200 normalizado, 401, 429, sem token, cache hit, fen inválida); frontend: painel renderiza linhas e chama `onPlay`, mostra aviso sem token; settings: token nunca exibido de volta (campo vazio com "token configurado" quando `lichess_token_set`).
- Commit: `feat(analise): livro de aberturas do Lichess com token pessoal`.
