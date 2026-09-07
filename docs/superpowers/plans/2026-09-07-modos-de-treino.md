# Modos de treino: repetição só revisa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repetição espaçada só serve exercícios já feitos ao menos uma vez e vencidos; a primeira vez acontece em "Novos (meus erros)", em "Treinar este estudo" ou ao guardar uma tática do Lichess. Ordem aleatória dos novos e embaralhamento dos vencidos do mesmo dia.

**Spec (aprovado em conversa, 2026-09-07):**
- **Repetição espaçada** (`mode=review`): só puzzles com `srs_due_at` definido (já revisados), `srs_due_at ≤ agora`, `in_queue`, não sanguessuga, de qualquer fonte (filtros `sources`, `category`, `theme`, `kind`, `color` continuam valendo). Ordem: por dia de vencimento (mais atrasado primeiro), embaralhados dentro do mesmo dia local. Nada de novos.
- **Novos (meus erros)** (`mode=new`): puzzles `source == "own"` nunca revisados (`srs_due_at IS NULL`), `in_queue`, não sanguessuga; limite = `new_per_day − novos revisados hoje` (como hoje); ordem conforme `new_order`: `"random"` (padrão) ou `"recent"` (partida mais recente primeiro). Filtros `category/theme/kind/color` valem.
- **Treinar este estudo** (`mode=study&study_id=`): todos os exercícios do estudo (`in_queue`, não sanguessuga), feitos ou não, na ordem dos capítulos (`StudyChapter.order`), sem limite diário. `due_count` = quantos deles estão vencidos.
- **Táticas do Lichess**: `POST /api/tactics/{id}/save` aceita `{correct?: bool, used_hint?: bool, duration_ms?: int}`; quando `correct` vem, o puzzle é criado e recebe imediatamente um `Review` com esse resultado (`record_review`), ficando agendado (acertou sem dica → 1 dia como acerto; senão → 1 dia como erro). Sem corpo, comportamento atual (entra sem revisão; aparecerá em "Novos"? Não: táticas guardadas sem resultado aparecem na repetição só depois da primeira revisão — para não perder o caso, o frontend sempre manda o resultado).
- **Painel**: `due_today` (review), `new_available` = novos dos seus erros, `new_remaining_today`; botão "Fazer novos" ao lado de "Treinar" (→ `/treinar?mode=new`); `by_source` inalterado.
- **Configuração** `new_order: "random" | "recent"` (padrão `random`) em Configurações ("Ordem dos novos: aleatória / mais recentes primeiro").
- **Sessão**: tela de início com o modo (Repetição espaçada / Novos (meus erros) / Táticas do Lichess) + seleção de estudo (que vira `mode=study`); `?mode=` e `?study=` na URL pré-selecionam. Mensagens de fila vazia por modo: review → "Nada vencido. Faça novos ou treine um estudo."; new → "Sem erros novos (ou limite diário atingido: N esperando amanhã)."; study → "Este estudo não tem exercícios na repetição.". No modo estudo, `orderInfo` = "capítulo N de M".

## Global Constraints
- Português; nunca "regerar/regeração". Suítes verdes (backend 435 hoje, frontend 364). Testes frontend só em `frontend/tests/**`. Commits com o trailer via `git commit -F`. Nada apaga dados; puzzles existentes continuam válidos (os `own` nunca revisados passam a aparecer em "Novos").

## Tasks

### Task 1 — backend: modos da fila, ordem e salvar tática com resultado
Files: `backend/chess_trainer/core/srs/queue.py` (`QueueFilters.mode: str = "review"`, `study_id`; `build_queue` por modo; `local_day_start` para agrupar por dia; `random` injetável via `rng` param para testes), `config.py` + `api/schemas.py` (`new_order`), `api/routes/training.py` (`GET /queue?mode=`, `QueueOut.mode`, dashboard), `api/routes/tactics.py` (`SaveTacticIn` opcional; `record_review` após criar/reativar), `api/schemas.py` (`QueueOut.mode`, `SaveTacticIn`), tests `tests/test_srs_queue.py`, `tests/test_api_training.py`, `tests/test_api_tactics.py`, `tests/test_config.py`. Regras conforme spec. `mode` inválido → 422. Commit `feat(treino): modos da fila (repetição, novos, estudo), ordem aleatória e tática guardada já agendada`.

### Task 2 — frontend: modos na sessão, painel, configurações
Files: `frontend/src/api/{types,client,queries}.ts` (`QueueFilters.mode`, `QueueOut.mode`, `api.saveTactic(id, body)`, `Settings.new_order`), `frontend/src/train/SessionStart.tsx` (modo com radios; estudo → study; `?mode=`/`?study=`; persistir `train.mode`), `frontend/src/train/TrainPage.tsx` (mensagens por modo; `orderInfo` do estudo; título "Novos (meus erros)"), `frontend/src/train/QueueButtons.tsx` + `TacticResultPanel.tsx` (guardar com o resultado da tentativa), `frontend/src/pages/DashboardPage.tsx` ("Fazer novos"), `frontend/src/pages/SettingsPage.tsx` (select `new_order`), `frontend/src/pages/StudiesPage.tsx`/`StudyDetailPage.tsx` (links "Treinar este estudo" → `/treinar?mode=study&study=<id>`), tests correspondentes em `frontend/tests/`. README: seção "Modos de treino". Commit `feat(treino): repetição só revisa; novos, estudo e táticas como primeira vez`.
