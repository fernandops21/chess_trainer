# Ciclo B1 (fontes de exercício) — pendências e medições da rodada final

Itens levantados na revisão final do branch `feat/fontes-de-exercicio` que
**não** foram corrigidos nessa rodada, mais o que a checagem de fumaça mediu.
Nada aqui é bloqueio de merge: são melhorias e riscos conhecidos.

## Pendências deferidas

- **Ordem de desempate dos capítulos novos** (`core/studies/service.py`,
  `upsert_study`): quando o PGN traz capítulos sem `ChapterURL`, o casamento é
  por `order`. Um capítulo inserido no meio do estudo desloca todos os
  seguintes e cada um "adota" o exercício do vizinho. Desempatar por
  `StudyChapter.order` + nome, ou exigir a URL, resolveria.
- **Semântica de `puzzles_total`** (`GET /api/dashboard`): hoje conta *todos*
  os exercícios, de todas as fontes e mesmo fora da fila. O painel mostra esse
  número ao lado de contagens que já são filtradas (`by_source`), o que confunde.
  Decidir se vira "na fila" ou se ganha um rótulo explícito.
- **Limpeza dos `.bak` e VACUUM** (`core/db.py`, `_copia_de_seguranca`): a
  migração deixa um `chess.db.bak-<timestamp>` por execução e nunca os remove;
  num banco de 437 MB isso soma rápido. Falta também um VACUUM depois do
  `_reconstruir_puzzles` (a tabela recriada deixa páginas livres).
- **Teste do tabuleiro com chessground de verdade** (`frontend/tests/board.test.tsx`):
  o dublê não simula `eraseOnClick`, então o teste do acúmulo de marcações no
  toque longo passaria mesmo com o bug. Hoje quem guarda a correção é a
  asserção sobre a config (`eraseOnClick === false` no ponteiro grosso). Um
  teste com o chessground real (jsdom + `getBoundingClientRect` mockado) cobriria
  o comportamento de verdade.
- **Guarda de `None` em `_download`** (`api/routes/studies.py`): `fetch_study_pgn`
  recebe `lichess_id: str | None`; hoje o chamador garante que não é `None`
  (sem PGN colado sempre há id), mas o tipo permite e um refactor futuro
  quebraria em silêncio.
- **Etiqueta de capítulo pulado na página de detalhe** (`StudyDetailPage.tsx`):
  o motivo do pulo só aparece na mensagem final do job, que some na próxima
  tarefa. O detalhe do estudo deveria marcar o capítulo (o backend precisaria
  guardar `skipped_reason` em `study_chapters`).

## Medições da checagem de fumaça

- **Migração do banco real** (cópia de 437 MB, esquema antigo de `puzzles`):
  cópia de segurança + reconstrução da tabela em poucos segundos, sem
  referência quebrada (`PRAGMA foreign_key_check` limpo).
- **Importação de estudo** (`lichess.org/study/4JKVAfaE`): 27 capítulos,
  15 exercícios, 0 pulados.
