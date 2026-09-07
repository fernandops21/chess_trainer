# Classificação automática de lances na Análise — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na Análise, classificar automaticamente cada lance do caminho atual no estilo chess.com (brilhante, ótimo, melhor, excelente, bom, livro, imprecisão, erro, blunder), com símbolo na lista de lances e um selo sobre a casa de destino do lance atual no tabuleiro.

**Spec (aprovado em conversa, 2026-09-07):** ver conversa ("simbolo de excelente e brilhante aparece?" → "Pode fazer sim").

## Regras

- Dados: `POST /api/analyse {fen, multipv: 3}` (já existe, depth 16, 3 s, cache LRU 500 no servidor; engine interativa com lock, então as chamadas serializam). Para cada nó `n` do caminho atual, `P` = posição pai (FEN), `C` = posição após o lance. `S_best` = `lines[0].score` de `P` (POV de quem joga em `P` = quem fez o lance); `s_child` = `lines[0].score` de `C` (POV do adversário) → avaliação do lance no POV do jogador = `−s_child`. `loss = S_best − (−s_child)` em cp; mates: score ±(100000−n) — tratar `|score| ≥ 90000` como ±3000 cp para a perda (clamp) e manter a categoria "melhor" quando o lance é o primeiro da engine.
- Categorias (prioridade nesta ordem; a primeira que casa vence):
  1. **livro** — nó em `bookIds` (base de mestres, hook `useBookMoves`), só enquanto a posição pai está no livro.
  2. **brilhante** (`!!`) — lance é o melhor da engine (`uci == lines[0].move` de `P`), é um sacrifício (material estático do jogador após a melhor resposta do adversário — primeiro lance de `lines[0].pv` de `C` aplicado com chess.js — cai ≥ 200 cp em relação a antes do lance, valores P=100 N=B=300 R=500 Q=900), e a avaliação após o lance não é perdedora (`−s_child ≥ −50`). Não conta captura/recaptura direta que apenas troca material (o cálculo após a resposta já cobre).
  3. **ótimo** (`!`) — lance é o melhor, `lines[1]` de `P` existe e `lines[0].score − lines[1].score ≥ 150` (única boa jogada), e `S_best ≤ 500` (não é posição já ganha).
  4. **melhor** (`★`) — `uci == lines[0].move` de `P`.
  5. **excelente** — `loss ≤ 20`.
  6. **bom** — `loss ≤ 50`.
  7. **imprecisão** (`?!`) — `loss ≤ mistake_threshold_cp` (configuração, 100).
  8. **erro** (`?`) — `loss ≤ blunder_threshold_cp` (200).
  9. **blunder** (`??`) — acima.
  Posições terminais (`terminal` na resposta) não classificam o lance seguinte (não há). Sem `lines` (engine indisponível) → sem classificação.
- Só o caminho atual (raiz → nó atual) é classificado, no máximo 60 meios-lances; a classificação é recalculada ao navegar (cache do React Query por FEN, `staleTime: Infinity`).
- Configuração: `Settings.classify_moves: bool` (padrão `true`) em Configurações → "Classificar lances na Análise (usa a engine)". Quando desligado, nada é consultado.
- Visual: na lista de lances (`MoveTreeView`), um selo pequeno após o SAN com o símbolo e cor (`brilhante` ciano, `ótimo` azul, `melhor`/`excelente` verde, `bom` cinza, `livro` como hoje, `imprecisão` amarelo, `erro` laranja, `blunder` vermelho); `title` com o nome em português. No tabuleiro, um selo circular sobre a casa de destino do **lance atual** (overlay posicionado sobre a casa, prop `badge?: { square: Key; text: string; className: string }` no `Board`, calculado a partir da orientação), como no chess.com. Os NAGs do autor continuam aparecendo (são outra coisa).
- Cabeçalho da Análise: "avaliação" continua; opcional: linha "lance: excelente (−0.12)" abaixo.

## Tasks

### Task 1: backend — `classify_moves` em Settings
Files: `backend/chess_trainer/config.py`, `api/schemas.py`, `tests/test_config.py`, `tests/test_api_system.py`. Campo `classify_moves: bool = True` em `AppSettings`/`SettingsOut`/`SettingsIn`. Testes de padrão e roundtrip. Commit `feat(config): opção de classificar lances na Análise`.

### Task 2: frontend — `classifyMove` puro + `useMoveClassification`
Files: create `frontend/src/analysis/classify.ts` (`classifyMove({ parent: AnalyseOut, child: AnalyseOut | null, uci, isBook, thresholds }) -> Classification | null` com `kind`, `label`, `symbol`, `loss`; `materialAfterReply(fenChild, replyUci, color)`; `pieceValue`), `frontend/src/analysis/useMoveClassification.ts` (`useQueries` de `api.analyse` para as FENs do caminho + a do nó atual, `enabled` só com `classify_moves` e ≤ 60 nós; devolve `Map<nodeId, Classification>`), tests `frontend/tests/classify.test.ts` (cada regra com dados sintéticos: melhor, excelente, bom, imprecisão, erro, blunder, ótimo, brilhante com sacrifício real — ex.: sacrifício de dama que leva a mate; mate scores), `frontend/tests/useMoveClassification.test.tsx` (mock de `api.analyse`, caminho de 3 lances, desligado por configuração → sem chamadas).

### Task 3: frontend — selos na lista e no tabuleiro + configuração
Files: `frontend/src/analysis/MoveTreeView.tsx` (prop `classes?: Map<string, Classification>`; selo após o SAN, com `title`), `frontend/src/analysis/AnalysisBoard.tsx` (usa `useSettings` + hooks; passa `classes` e `bookIds`; `badge` do lance atual para o `Board`; linha "lance: …" no cabeçalho), `frontend/src/board/Board.tsx` (prop `badge`, overlay posicionado: casa → `left/top` em % conforme orientação; `pointer-events: none`), `frontend/src/pages/SettingsPage.tsx` (checkbox), `frontend/src/styles/base.css` (cores dos selos), tests `moveTreeView.test.tsx`, `board.test.tsx` (badge posição para as duas orientações), `analysisBoard.test.tsx` (selos aparecem com `api.analyse` mockado; desligado → nenhum), `settingsPage.test.tsx`. README: seção "Classificação de lances". Commit `feat(analise): classificação automática dos lances com selos na lista e no tabuleiro`.

## Global Constraints
- Português; nunca "regerar/regeração". Suítes verdes (backend 434, frontend após o livro). Testes frontend só em `frontend/tests/**`. Commits com o trailer via `git commit -F`.
- Nada de chamadas à engine fora da Análise; nada quando `classify_moves` está desligado.
