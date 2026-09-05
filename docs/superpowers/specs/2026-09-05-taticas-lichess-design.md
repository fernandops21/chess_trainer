# Chess Trainer — Banco de táticas do Lichess e estatísticas por tema

Data: 2026-09-05
Status: proposto pelo assistente durante janela de autonomia de 30 h (usuário ausente); executar e apresentar.
Depende de: ciclo A (backend, frontend) e "evitar completo e análise", todos na `main`.

## 1. Motivação

Os puzzles dos próprios erros são o diferencial do produto, mas são poucos
(uma partida rende de 0 a 5) e dependem de análise cara. O Lichess publica,
em domínio público (CC0), um banco com ~4 milhões de puzzles táticos com
rating, popularidade e temas. Integrá-lo dá ao app treino ilimitado, calibrado
pelo nível do usuário e filtrável por tema, e permite estatísticas do tipo
"você erra garfos de cavalo" cruzando os dois tipos de puzzle. Esse era o
primeiro item das "fases futuras" do spec do ciclo A.

## 2. Dados

- Fonte: `https://database.lichess.org/lichess_db_puzzle.csv.zst` (~250 MB
  comprimido, ~900 MB CSV). Colunas: `PuzzleId, FEN, Moves, Rating,
  RatingDeviation, Popularity, NbPlays, Themes, GameUrl, OpeningTags`.
  `FEN` é a posição **antes** do lance do adversário; `Moves` (UCI, separados
  por espaço) começa com esse lance do adversário e depois alterna solver /
  adversário até o fim do puzzle.
- Importação com filtro (configurável): `NbPlays ≥ lichess_min_plays` (padrão
  2000) e `Popularity ≥ lichess_min_popularity` (padrão 90), rating entre 400 e
  3000. Estimativa: ~1 milhão de puzzles (medido em 6,1 milhões de linhas; com
  o filtro antigo de 200/60 seriam ~3,9 milhões e um banco de 1,6 GB).
- Tabelas novas (SQLite, mesmo banco):
  - `lichess_puzzles(id TEXT PK, fen, moves, rating INT, rating_deviation INT,
    popularity INT, nb_plays INT, themes TEXT, opening_tags TEXT)`, índice em
    `rating`.
  - `lichess_puzzle_themes(theme TEXT, puzzle_id TEXT)`, índice em
    `(theme, puzzle_id)`.
  - `tactics_attempts(id, puzzle_id, attempted_at, correct BOOL, used_hint
    BOOL, duration_ms INT, rating_before INT, rating_after INT,
    puzzle_rating INT, session_id NULL)`.
- Estado do importador em `Setting`: `lichess_imported_at`, `lichess_count`,
  `lichess_source_rows`.
- Configurações novas: `tactics_rating` (inicial 1200), `tactics_window`
  (±150), `lichess_min_plays` (2000), `lichess_min_popularity` (90).
- Importação é um job (`import_lichess`) do `JobRunner`: baixa o arquivo para
  `backend/data/` (pulando se já existe e tem o tamanho certo), descomprime em
  streaming (`zstandard`), filtra, insere em lotes de 5 000 com
  `INSERT OR IGNORE`, progresso por linhas lidas. Cancelável entre lotes;
  idempotente (rodar de novo completa o que faltou).

## 3. Seleção de puzzles ("Táticas")

- `pick_next(db, settings, themes=[], exclude=[])`:
  1. Candidatos com `rating` em `[tactics_rating − window, tactics_rating +
     window]` (alarga a janela em passos de 100 até achar candidatos).
  2. Se houver temas, exige pelo menos um em `lichess_puzzle_themes`.
  3. Exclui puzzles com tentativa correta; puzzles errados há mais de 1 dia
     têm prioridade (“errados primeiro”) sobre nunca vistos; os da lista
     `exclude` (já servidos na sessão) ficam de fora.
  4. Sorteio uniforme dentro do conjunto (LIMIT 50 aleatório por `random()`).
- Conversão para o formato de treino: aplica `Moves[0]` ao `FEN` para obter
  `fen_start`; `side_to_move` = lado a jogar; solução = `Moves[1:]` alternando
  `solver`/`engine`; `end_reason` = `mate` se o último lance dá mate, senão
  `material_gain`; `theme` = primeiro tema "tático" reconhecido (mapa de
  tradução), os demais em `themes`; `lichess_url = https://lichess.org/training/{id}`.
- Rating do usuário (Elo simplificado, K = 32): esperado
  `E = 1 / (1 + 10^((R_puzzle − R_user)/400))`; `R_user += K × (S − E)`, com
  `S = 1` se acertou sem dica e `0` caso contrário. Guardado em
  `tactics_rating`; cada tentativa registra antes/depois.

## 4. API

- `GET /api/tactics/status` → `{imported: bool, count, imported_at, rating,
  window, attempts_total, attempts_today}`.
- `POST /api/tactics/import` → 202 (job `import_lichess`); 409 se ocupado.
- `GET /api/tactics/next?themes=a,b&exclude=id1,id2` → `TacticOut` ou 404
  quando não há candidatos (mensagem explica: banco não importado / filtros).
- `POST /api/tactics/attempts` `{puzzle_id, correct, used_hint, duration_ms,
  session_id?}` → `{rating_before, rating_after, delta, puzzle_rating}`.
- `GET /api/tactics/themes` → lista de temas com contagem (para o filtro).
- `GET /api/stats/themes?days=30` → por tema: tentativas, acertos, taxa,
  combinando `Review` dos puzzles próprios (tema do `Puzzle`) e
  `tactics_attempts` (primeiro tema traduzido), ordenado por tentativas.

## 5. Interface

- **Treinar** ganha a escolha da fonte no painel de início: "Meus erros"
  (fluxo atual) ou "Táticas do Lichess" (novo), mais o filtro de temas (chips
  com os 20 temas mais comuns, traduzidos) e o relógio como hoje.
- Sessão de táticas: cabeçalho com o rating atual e o rating do puzzle;
  puzzle resolvido no mesmo `PuzzleView`/`usePuzzle`; resultado mostra
  acerto/erro, `±delta` de rating, tema(s), link "ver no Lichess", botão
  Explorar e Próximo. Fila infinita: cada Próximo pede `/api/tactics/next`
  com os temas e os ids já vistos na sessão. Resumo da sessão como hoje, com
  o rating inicial → final.
- **Painel**: cartão "Táticas" com rating, tentativas hoje e taxa de acerto
  dos últimos 30 dias; cartão "Por tema" com barras simples (taxa de acerto
  por tema, próprios + Lichess) e o tema mais fraco em destaque.
- **Configurações**: seção "Banco de táticas (Lichess)": estado (não
  importado / N puzzles importados em data), botão "Baixar e importar"
  (mostra progresso pelo cartão de tarefas), campos de filtro e o rating
  inicial / janela.
- Erros comuns tratados: banco não importado (Treinar mostra o aviso com link
  para Configurações), sem candidatos com os filtros (mensagem e botão para
  limpar temas).

## 6. Testes

- Backend: importador com fixture `.csv.zst` gerada no teste (`zstandard`),
  filtro, idempotência, progresso e cancelamento; conversão de puzzle
  (primeiro lance aplicado, alternância, mate); `pick_next` (janela, temas,
  exclusões, errados primeiro, alargamento); Elo; rotas; estatísticas por tema.
- Frontend: adaptador `PuzzleLike` (próprio vs tática) em `usePuzzle`;
  `PuzzleView`/`ResultPanel` sem `game`; sessão de táticas (mock de fetch):
  próximo puzzle, rating delta, fim.
- Manual: importar o banco de verdade, treinar 5 táticas no desktop e no
  celular, conferir o Painel e as Configurações.

## 7. Fora de escopo

Glicko completo, campanhas por tema (streaks), puzzles do Lichess dentro da
fila de repetição espaçada, temas de abertura (`OpeningTags`) como filtro.
