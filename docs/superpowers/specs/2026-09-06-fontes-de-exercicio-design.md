# Chess Trainer — Ciclo B1: fontes de exercício, estudos do Lichess, último lance e marcações

Data: 2026-09-06
Status: aprovado em conversa (seções 1–5); execução autorizada sem novas perguntas.
Depende de: ciclo A, "evitar completo e análise" e "táticas do Lichess", todos na `main`.
Próximo: ciclo B2 (editor de estudos), spec separado.

## 1. Motivação

O usuário quer que a repetição espaçada seja a camada sobre qualquer fonte de
exercício, não só sobre os erros das próprias partidas: táticas do Lichess que
valem repetir, e exercícios das aulas que segue (estudos do Lichess do
professor, ex.: https://lichess.org/study/4JKVAfaE, 27 capítulos em modo
"gamebook"). Além disso, duas convenções das outras plataformas que fazem
falta: ver o último lance do adversário antes de jogar e desenhar setas e
casas com o botão direito.

## 2. Modelo de dados: exercício com fonte

- `Puzzle` ganha:
  - `source: str` — `own` | `lichess` | `study` (padrão `own`; todos os
    puzzles existentes ficam `own`).
  - `in_queue: bool` (padrão `true`). Fora da fila o puzzle e seu histórico
    ficam; ele só não é servido nem contado.
  - `external_id: str | None` (id do puzzle do Lichess), único quando
    presente.
  - `chapter_id: str | None` → `study_chapters.id`.
  - `position_id` e `game_id` passam a ser opcionais (nulos fora de `own`).
    A restrição única `(fen_start, kind)` passa a `(fen_start, kind,
    source)`; puzzles `lichess`/`study` usam `kind = "punish"` por
    compatibilidade da interface (solver = lado a mover na posição inicial)
    e `theme` = tema principal traduzido (Lichess) ou `study`.
  - `solution` ganha, opcionalmente, `wrong_moves: {uci: comentário}` (lances
    errados previstos pelo autor do estudo, com o comentário dele) e
    `comments: {índice_do_lance: comentário}` (comentários da linha
    principal, mostrados no resultado).
- `Study(id, title, author, source_url, lichess_id, imported_at, created_at,
  updated_at)` e `StudyChapter(id, study_id, order, name, lichess_url (único
  quando presente), fen, orientation, mode ("gamebook" | "read"), pgn,
  intro_comment, puzzle_id | None, in_queue)`.
- Último lance: `PuzzleOut` ganha `fen_before` e `last_move` (UCI), ambos
  opcionais, calculados na saída:
  - `own` punir: `Position.fen` e `Position.move_uci` (o erro do adversário);
  - `own` evitar: a posição de ply−1 da mesma partida (lance do adversário
    antes do erro do usuário); sem ply−1 (ply 1), nulos;
  - `lichess`: gravados no puzzle ao guardar (`fen_before` = FEN do banco,
    `last_move` = `Moves[0]`), em colunas novas `fen_before`, `last_move`;
  - `study`: nulos, salvo quando o capítulo tem um lance antes da posição
    (não há no formato do Lichess; ficam nulos).
- Migração: `init_db` continua `create_all` para tabelas novas; para colunas
  novas em `puzzles`, uma função `migrate(engine)` em `core/db.py` adiciona
  as colunas ausentes com `ALTER TABLE … ADD COLUMN` e padrões
  (`source='own'`, `in_queue=1`) e recria a restrição única via índice único
  novo (`uq_puzzle_fen_kind_source`), mantendo o índice antigo se já existir
  (SQLite não remove restrições inline; o índice antigo `(fen_start, kind)`
  fica e não atrapalha porque puzzles `lichess`/`study` nunca colidem com
  posições de partidas do usuário — e, se colidirem, o guardar devolve o
  puzzle existente). Testada abrindo um banco de fixture do esquema anterior.

## 3. Fila única, filtros, guardar e tirar

- `QueueFilters` ganha `sources: list[str]` (vazio = todas) e `study_id`.
  Fila e painel só consideram `in_queue = true` e `is_leech = false`.
- Limite diário de novos compartilhado; ordem dos novos inalterada (mais
  recentes primeiro); com `study_id`, só os do estudo contam.
- `POST /api/puzzles/{id}/queue {in_queue}`: tirar/voltar. Não apaga nada.
- `POST /api/tactics/{lichess_id}/save`: cria (ou devolve, se já existe) o
  `Puzzle` fonte `lichess` com a solução convertida por `to_tactic`,
  `in_queue = true`, `category = "lichess"`, `theme` = tema principal.
  Resposta: `PuzzleOut`. `TacticOut` ganha `saved: bool` (existe puzzle com
  esse `external_id` e `in_queue`).
- Uma tática guardada e resolvida na fila registra `Review` (repetição), não
  `TacticsAttempt` (o rating só se move na sessão de táticas).
- Painel: contadores somam todas as fontes; `DashboardOut.by_source` =
  `{own, lichess, study}` com `in_queue` e vencidos por fonte; cartão
  "Estado" mostra "N dos seus erros · N do Lichess · N de estudos".
- Revisão de erros continua listando os `own` mesmo fora da fila, com a
  etiqueta "fora da repetição".

## 4. Último lance animado e marcações

- Tabuleiro do puzzle: se `fen_before` e `last_move` existem, monta em
  `fen_before`, espera 400 ms, anima o lance (chessground) com destaque de
  origem/destino e só então libera as peças; o relógio de duração do puzzle
  começa após a animação. Sem último lance, começa direto. Vale na fila, na
  sessão de táticas e em "Treinar este". No resultado, a linha navegável
  começa em `fen_before` com o último lance como posição 0 (numeração
  correta); sem último lance, como hoje.
- Marcações (chessground `drawable`): botão direito arrastando = seta;
  clique direito = casa; repetir apaga; clique esquerdo limpa tudo; Shift/
  Alt/Ctrl trocam a cor (verde, vermelho, azul, amarelo). Toque longo no
  celular. Ligado no tabuleiro do puzzle, na linha do resultado e no
  tabuleiro de análise. Marcações não são salvas e somem ao trocar de
  puzzle/posição.
- Setas e casas do autor (`[%cal …]`/`[%csl …]` nos comentários do estudo):
  extraídas na importação para `solution.shapes: {índice: [{orig, dest?,
  brush}]}`; mostradas na linha do resultado no lance correspondente e no
  tabuleiro do puzzle apenas na posição inicial (índice 0), como dica visual
  do autor.

## 5. Importar estudos do Lichess

- Tela **Estudos** (menu): lista de estudos com autor, capítulos, quantos na
  fila, vencidos hoje; botões "Treinar este estudo" (abre Treinar com
  `study_id`), "Reimportar", "Tirar da repetição"/"Voltar para a repetição"
  (todos os capítulos), "Remover" (apaga estudo, capítulos, puzzles e
  histórico, com confirmação). Detalhe do estudo: capítulos em ordem, com
  modo, "Treinar este" e "ver no Lichess".
- "Importar do Lichess": campo de URL (`lichess.org/study/<id>` ou
  `/study/<id>/<capítulo>`) ou área para colar PGN exportado (estudos
  privados). Job `import_study`: `GET https://lichess.org/api/study/{id}.pgn`
  (redirecionamentos seguidos, 30 s), separa os jogos do PGN com
  python-chess, monta os capítulos:
  - `[ChapterMode "gamebook"]` → `mode = gamebook` → vira puzzle;
    capítulos sem esse header (partidas anotadas, texto) → `mode = read`,
    sem puzzle (editáveis no B2).
  - Solver = lado a mover na FEN inicial (se a `[Orientation]` divergir,
    prevalece o lado a mover). Solução = linha principal inteira do autor,
    alternando `solver`/`engine`; variações no lance do solver com comentário
    → `wrong_moves`; comentários da linha principal → `comments`;
    `%cal`/`%csl` → `shapes`; comentário antes do primeiro lance →
    `intro_comment` (mostrado no cabeçalho do puzzle como enunciado).
  - Capítulo sem lances → `read`. Lance ilegal → capítulo pulado e listado na
    mensagem final do job.
- Idempotência: chave do capítulo = `lichess_url`. Reimportar atualiza
  título/nomes/linhas; linha principal alterada atualiza `solution` e
  `fen_start` do puzzle mantendo id e histórico; capítulos ausentes na nova
  versão ficam `in_queue = false` (não apagados).
- Erros: URL inválida → 400; estudo privado/inexistente (404 do Lichess) →
  job termina em erro com a mensagem "estudo privado ou inexistente; exporte
  o PGN no Lichess e cole aqui"; PGN sem capítulo válido → erro claro.
- Ficha e resultado de puzzle `study` mostram "Estudo · Capítulo" e o link
  do capítulo.

## 6. API (resumo)

- `GET /api/queue?sources=own,lichess&study_id=` ; `GET /api/dashboard`
  com `by_source`.
- `POST /api/puzzles/{id}/queue`, `POST /api/tactics/{lichess_id}/save`.
- `GET /api/studies`, `GET /api/studies/{id}`, `POST /api/studies/import`
  (`{url}` ou `{pgn}`, 202), `POST /api/studies/{id}/reimport` (202),
  `POST /api/studies/{id}/queue {in_queue}`, `DELETE /api/studies/{id}`.
- `PuzzleOut`: `source`, `in_queue`, `fen_before`, `last_move`, `study:
  {id, title, chapter_id, chapter_name, lichess_url} | null`, `game`,
  `mistake`, `ply`, `move_played` opcionais (nulos fora de `own`);
  `solution.wrong_moves`, `solution.comments`, `solution.shapes` opcionais.
- `TacticOut.saved`.

## 7. Interface (resumo)

- Treinar: painel de início com fontes (chips "Meus erros", "Lichess
  guardados", "Estudos") e, com "Estudos", seleção de um estudo; `?study=`
  na URL pré-seleciona.
- Resultado: "Guardar para repetir"/"Guardado ✓" (táticas do Lichess),
  "Tirar da repetição"/"Voltar para a repetição" (puzzles da fila);
  comentários do autor lance a lance; ao jogar um lance errado previsto, a
  mensagem de erro mostra o comentário do autor.
- Cabeçalho do puzzle `study`: enunciado (`intro_comment`) e "Estudo ·
  Capítulo".
- Menu: item "Estudos".

## 8. Testes

- Backend: migração em banco de fixture antigo; fila por fonte/estudo;
  guardar tática idempotente; tirar/voltar; `fen_before`/`last_move` para
  punir, evitar (ply 1 → nulo), lichess; parser de estudo com o PGN real
  (`tests/fixtures/study_4JKVAfaE.pgn`, 27 capítulos): contagem de gamebook
  vs read, solução, `wrong_moves`, `comments`, `shapes`, `intro_comment`;
  reimport (linha alterada, capítulo removido); 404 do Lichess → erro
  legível; rotas.
- Frontend: animação do último lance (bloqueio até animar, relógio após);
  marcações ligadas; guardar/tirar; filtro por fonte; tela Estudos; resultado
  com comentários e feedback de erro previsto; `PuzzleView` sem `game`.
- Manual: importar o estudo do Basso, treinar dois capítulos no celular,
  guardar uma tática e vê-la na fila.

## 9. Fora de escopo

Editor de estudos (B2), salvar marcações, contas e compartilhamento, rating
para exercícios de estudo, importar puzzles do chess.com, capítulos `read`
como leitura navegável (B2).
