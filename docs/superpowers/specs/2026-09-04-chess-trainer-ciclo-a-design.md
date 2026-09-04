# Chess Trainer — Ciclo A: importar → analisar → treinar meus erros

Data: 2026-09-04
Status: aprovado em conversa, aguardando revisão do spec escrito

## 1. Visão

Um app de xadrez pessoal cujo eixo é: **repetição espaçada sobre os seus
próprios erros**. "Chessable, mas o curso é você mesmo."

Grandes plataformas cobrem partes disso, nenhuma cobre o conjunto:

| | Táticas do banco geral | Puzzles dos seus erros | Repetição espaçada |
|---|---|---|---|
| Lichess | sim | só "learn from your mistakes", uma vez | não |
| Chess.com | sim | não | não |
| Chessable | alguns cursos | não | sim, sobre cursos comprados |

Este spec cobre o **primeiro ciclo** (ciclo A): importar partidas do
chess.com, analisar com Stockfish, gerar puzzles a partir dos erros
(seus e do adversário), e treinar esses puzzles com repetição espaçada.

Fases futuras, fora deste spec: treinador com o banco de táticas do
Lichess, repertório/erros de abertura, banco de jogos de GMs, jogar
contra a engine, multiusuário/hospedagem, erros posicionais.

### Decisões de escopo já tomadas

- Roda **local**, um usuário, mas com fronteira clara núcleo ↔ API para
  virar produto hospedado depois. IDs são UUID.
- **Python** no backend (núcleo + FastAPI + SQLite), **React +
  TypeScript + Vite** no frontend, **chessground** para o tabuleiro,
  **chess.js** para validação de lances no cliente, **python-chess** e
  **Stockfish** (binário nativo, via UCI) no núcleo.
- Importação por padrão de **rapid, daily e classical**; bullet e blitz
  disponíveis, desligados.
- Puzzles têm **vários lances** e **só terminam quando o ganho se
  materializa** (mate ou captura concreta). Ao terminar, a linha inteira
  da engine é mostrada.
- Puzzles do seu próprio blunder são jogados **do lado do adversário**
  ("punir"). Puzzle "evitar" (achar o lance certo antes do blunder) só
  quando há um lance claramente melhor.

## 2. Arquitetura

```
chess-trainer/
  backend/
    chess_trainer/
      core/            # sem dependência de web; testável isolado
        importers/     # chess.com
        analysis/      # engine, replay de partida, detecção de erros
        puzzles/       # geração, materialização, temas, dedup
        srs/           # repetição espaçada (funções puras)
        models.py      # SQLAlchemy
        db.py
      api/             # FastAPI: rotas, fila de tarefas, arquivos estáticos
      config.py        # configurações locais (usuário, stockfish, limiares)
    tests/
  frontend/            # Vite + React + TS
  docs/superpowers/specs/
```

- Um processo: `uvicorn` serve a API e, se `frontend/dist` existir, os
  estáticos. Em desenvolvimento, Vite roda separado com proxy para a API.
- Tarefas longas (importar, analisar, gerar puzzles) rodam numa **fila em
  segundo plano** dentro do processo, uma por vez, com progresso
  consultável pela API.
- O núcleo nunca importa nada de `api/`. A API é uma camada fina que
  chama funções do núcleo. Para hospedar: trocar SQLite por Postgres
  (SQLAlchemy) e acrescentar `user_id` às tabelas.

## 3. Modelo de dados

```
Game      id, source ("chess.com"), source_id (URL da partida, único),
          pgn, white, black, result, time_control (string bruta),
          category (bullet|blitz|rapid|daily|classical), played_at,
          my_color (white|black), imported_at, analyzed_at (nullable),
          analysis_depth (nullable)

Position  id, game_id, ply, fen (antes do lance), move_played (SAN),
          move_uci,
          eval_before (cp ou mate, do ponto de vista de quem joga),
          eval_after, best_move (UCI), best_eval,
          is_mistake (bool), mistake_level (mistake|blunder|null),
          mistake_by (me|opponent|null)

Puzzle    id, position_id, game_id, kind (punish|avoid), fen_start, side_to_move,
          solution (JSON: lista de lances UCI alternando solver/engine,
          com alternativas válidas por lance do solver),
          end_reason (mate|material_gain|explanation),
          theme (mate_in_n|fork|hanging_piece|pin|discovered_attack|
          tactic), category (copiada da partida, para filtro),
          solver_moves (int), created_at, is_leech (bool),
          leech_since (nullable),
          srs_ease, srs_interval_days, srs_lapses, srs_due_at,
          srs_last_reviewed_at   ← estado SRS atual (cache)

Review    id, puzzle_id, session_id, reviewed_at, result (correct|wrong),
          used_hint (bool), duration_ms,
          ease, interval_days, due_at, lapses   ← estado SRS após esta revisão

Session   id, started_at, ended_at (nullable), planned_minutes (nullable),
          filters (JSON)

Settings  chave/valor: chesscom_username, categories, stockfish_path,
          analysis_depth (18), puzzle_depth (20),
          mistake_threshold_cp (100), blunder_threshold_cp (200),
          avoid_gap_cp (150), new_per_day (10), leech_lapses (5)
```

- `Position` guarda a análise inteira da partida, não só os erros.
  Reprocessar a detecção de erros ou regerar puzzles não exige rodar a
  engine de novo.
- `Puzzle` deriva de `Position`; `Review` deriva de `Puzzle`. O estado
  atual de SRS fica **em cache no `Puzzle`** (`srs_ease`,
  `srs_interval_days`, `srs_lapses`, `srs_due_at`,
  `srs_last_reviewed_at`); cada `Review` é o registro histórico de uma
  resolução e repete o estado resultante. Puzzle com `srs_due_at` nulo é
  "novo".
- Dedup: `fen_start + kind` é único em `Puzzle`.

## 4. Importação (chess.com)

- API pública, sem autenticação:
  `GET https://api.chess.com/pub/player/{user}/games/archives` lista os
  meses; `GET .../games/{yyyy}/{mm}` devolve as partidas com PGN.
  O nome de usuário deve ser enviado em **minúsculas** (a API rejeita
  `theRealZibs`, aceita `therealzibs`); normalizar ao salvar a
  configuração. Usuário do autor: `therealzibs` (16 meses de arquivo
  desde 2023-05).
- Percorre os meses a partir do último importado (incremental). Para
  cada partida: pula se `source_id` já existe; `category` é o campo
  `time_class` do chess.com (bullet/blitz/rapid/daily); o valor
  `classical` existe no modelo só para fontes futuras; aplica o filtro
  de categorias; pula variantes (campo `rules` ≠ "chess") com aviso;
  grava `Game` com `my_color` a partir do nome de usuário.
- `User-Agent` identificando o app (exigência do chess.com).
- Erro de rede ou HTTP 429: a tarefa para com mensagem e o próximo
  "Importar agora" retoma do mesmo mês.

## 5. Análise (Stockfish)

- Localização do binário: `stockfish_path` das configurações, senão
  `stockfish` no PATH. Se não encontrar, a API devolve estado
  "engine ausente" e a interface mostra instruções de download.
- Para cada `Game` sem `analyzed_at`: replay do PGN com python-chess.
  Em cada posição (incluindo a final), avaliação com profundidade fixa
  `analysis_depth`. Grava uma `Position` por lance com `eval_before`
  (avaliação da posição antes do lance, do ponto de vista de quem vai
  jogar), `eval_after` (avaliação após o lance, mesmo ponto de vista),
  `best_move` e `best_eval`.
- Convenção de avaliação: centipawns inteiros; mate representado como
  `±(100000 - n)` para mate em n, de modo que comparações numéricas
  funcionem.
- Uma partida por vez, uma instância de engine reutilizada. Se a engine
  morrer, a partida fica sem `analyzed_at` e volta à fila; a engine é
  reiniciada.
- Ao concluir a partida: detecção de erros e geração de puzzles rodam
  em sequência, na mesma tarefa.

## 6. Detecção de erros

Função pura sobre a lista de `Position` de uma partida. Para cada lance,
`drop = eval_before - eval_after` (ambos do ponto de vista de quem jogou):

- `blunder` se `drop ≥ blunder_threshold_cp`, ou se havia mate a favor e
  deixou de haver, ou se não havia mate contra e passou a haver.
- `mistake` se `mistake_threshold_cp ≤ drop < blunder_threshold_cp`.
- Caso contrário, não é erro.
- Exceção: se `eval_before` já era decisivamente perdido (≤ -1000 cp)
  ou decisivamente ganho (≥ +1000 cp) e continua no mesmo lado após o
  lance, não marca erro (a queda não muda o resultado).

`mistake_by` = `me` se quem jogou é `my_color`, senão `opponent`.

## 7. Geração de puzzles

Roda por `Position` marcada como erro. Usa a engine com `puzzle_depth`
e multipv = 3.

### 7.1 Puzzle "punir" (todo erro, seu ou do adversário)

- Início: posição **após** o lance errado. Solver joga o lado que pune
  (se o erro foi seu, o solver joga com as peças do adversário).
- Linha principal da engine estendida até a **materialização**:
  - Se `best_eval` indica mate em n: solução vai até o mate. Sem exceção.
  - Senão: acompanha a linha contando material capturado por cada lado.
    A solução termina no lance do solver após o qual o saldo de material
    a favor do solver, somado desde o início do puzzle, é ≥ ao ganho
    esperado (`eval_after` convertido em peões, arredondado para baixo
    para o valor de peça mais próximo: 1, 3, 5, 9) **e** a posição está
    quieta (nenhuma recaptura imediata devolve o material).
  - O ganho esperado é o **menor** entre a queda de avaliação do erro e a
    avaliação da engine para o solver na posição inicial do puzzle: perder
    um mate ou uma vantagem posicional enorme não pode exigir o ganho de
    uma dama quando a posição só vale, por exemplo, +3.
  - Se em até 10 lances do solver não materializa: puzzle **descartado**.
- Só gera se, na posição inicial, a avaliação para o solver é ≥ +100 cp
  ou mate a favor. (Se o erro foi "perder um mate" mas o lado que errou
  segue ganhando, não há o que punir.)
- Unicidade por lance do solver (multipv = 3, janela de 50 cp):
  - No **lance final** (o que materializa), um alternativo dentro da
    janela que também materializa (mate em 1, ou captura que atinge o
    ganho e sobrevive à melhor resposta) é aceito como resposta
    alternativa; um alternativo dentro da janela que **não** materializa
    descarta o puzzle.
  - Em **lances intermediários**, qualquer alternativo dentro da janela
    descarta o puzzle: se o solver desviar, a linha não continua.
- Mates com mais de 15 lances do solver são descartados (limite prático).
- Se a linha termina em fim de jogo que não é mate (afogamento, etc.),
  o puzzle é descartado.
- Lances do defensor: sempre a melhor defesa da engine. Ao resolver, o
  solver só responde pelos lances dele.
- **Puzzles triviais**: peça de valor ≥ 3 deixada de graça na própria
  casa de destino do lance errado (indefesa, ou atacada por uma peça do
  solver que vale menos que ela), sem nada maior por trás (avaliação do
  solver não indica mate nem vantagem além do valor dessa peça), não
  vira puzzle "punir". Peças de valor < 3 (peão) não entram nessa regra.

### 7.2 Puzzle "evitar" (só nos seus erros)

- Início: posição **antes** do seu lance errado, com as suas peças.
- Gerado só se `best_eval - segundo_melhor_eval ≥ avoid_gap_cp`.
- Solução: um lance (o melhor). `end_reason = explanation`: ao resolver,
  mostra a continuação da engine (linha principal, até 6 lances) como
  explicação. Sem regra de materialização.

### 7.3 Tema

Inferido por regras sobre a solução; primeira que bater:

- `mate_in_n`: fim em mate.
- `hanging_piece`: primeiro lance do solver captura uma peça não defendida.
- `fork`: após o primeiro lance do solver, a peça movida ataca duas ou
  mais peças de valor maior ou o rei.
- `pin`: primeiro lance cria uma cravada absoluta ou relativa que ganha
  material na linha.
- `discovered_attack`: o primeiro lance do solver descobre um ataque de
  outra peça.
- Senão: `tactic`.

### 7.4 Regeneração

"Regerar puzzles" nas configurações apaga `Puzzle` (e `Review`) e roda a
detecção e geração de novo sobre as `Position` existentes. Aviso na
interface de que o histórico de treino se perde.

## 8. Repetição espaçada (SRS)

SM-2 adaptado, implementado como função pura
`next_state(previous, result, used_hint, duration_ms, reviewed_at)`.

- Estado inicial (puzzle novo): `ease = 2.5`, `interval = 0`,
  `lapses = 0`.
- **Errou** ou **usou dica** (dica conta como erro): `interval = 1`,
  `ease = max(1.3, ease - 0.2)`, `lapses += 1`.
- **Acertou**: se `interval == 0` → 1 dia; se 1 → 3; senão
  `interval = round(interval_real * ease)`, onde `interval_real` é o
  tempo efetivamente decorrido desde a revisão anterior (atraso conta a
  favor). `ease += 0.1` se acertou rápido (`duration_ms` ≤ 10 s por
  lance do solver), senão inalterada.
- `due_at = reviewed_at + interval dias`.
- Datas: todas em UTC, armazenadas sem fuso; "hoje" para o limite de
  novos por dia e para a sequência de dias usa a meia-noite local.
- **Sanguessuga**: quando `lapses` atinge `leech_lapses` (5), o puzzle
  recebe `is_leech = true` e sai da fila. Aparece na tela de revisão de
  erros; "devolver à fila" zera `srs_lapses`, mantém `srs_ease`,
  `srs_due_at = agora`, `is_leech = false`.

Fila do dia (`GET /api/queue`):

1. Puzzles com `due_at ≤ agora` e não sanguessuga, mais atrasados
   primeiro.
2. Só quando a lista 1 está vazia: puzzles novos, das partidas mais
   recentes primeiro, limitados a `new_per_day` menos os novos já
   revisados hoje.
3. Filtros opcionais: categoria, tema, kind, cor do solver.

Uma resolução = uma `Review`. Errar um lance dentro do puzzle: o app
avisa, desfaz e deixa tentar de novo; o puzzle já está marcado como
`wrong`, mas continua até o fim.

Sessão: `POST /api/sessions` cria uma `Session` com filtros e
`planned_minutes` opcional. Cada `Review` referencia a sessão. Ao zerar
o relógio, o frontend termina o puzzle atual e pergunta "continuar ou
encerrar"; continuar segue na mesma sessão com o relógio contando para
cima; encerrar grava `ended_at` e mostra o resumo.

## 9. API

```
GET  /api/status                 engine ok?, importação/análise em andamento, progresso
GET  /api/settings  PUT /api/settings
POST /api/import                 enfileira importação
POST /api/analyze                enfileira análise das partidas pendentes
POST /api/puzzles/regenerate

GET  /api/games?category=&color=&result=&analyzed=
GET  /api/games/{id}             partida + positions (avaliações, erros)

GET  /api/mistakes?level=&theme=&category=&by=
GET  /api/puzzles/{id}
GET  /api/queue?category=&theme=&kind=&color=
GET  /api/leeches   POST /api/puzzles/{id}/unleech

POST /api/sessions               {planned_minutes?, filters}
POST /api/sessions/{id}/end
POST /api/reviews                {puzzle_id, session_id, result, used_hint, duration_ms}
GET  /api/dashboard              vencidos hoje, novos disponíveis, sequência de dias, última importação
```

## 10. Interface

Navegação lateral com cinco telas:

1. **Painel**: vencidos hoje, novos disponíveis, sequência de dias,
   botão "Treinar", status de importação/análise com progresso, "Importar
   agora", "Analisar pendentes".
2. **Treinar**: ao entrar, escolhe filtros e "até acabar a fila" ou "N
   minutos". Tabuleiro grande orientado para o lado do solver, texto
   "Brancas jogam · punir o erro" / "Pretas jogam · evitar o erro",
   relógio da sessão, botão de dica (destaca a peça; conta como erro).
   Lance certo: a engine responde automaticamente. Lance errado: aviso,
   desfaz. Fim do puzzle: linha completa da engine navegável no
   tabuleiro, tema, link para a partida original, botão "Próximo".
   Tempo esgotado: "continuar ou encerrar". Fim da sessão: resumo
   (puzzles, acertos, tempo).
3. **Partidas**: lista com filtros; ao abrir, tabuleiro com navegação
   lance a lance, gráfico de avaliação, lances de erro marcados e
   clicáveis.
4. **Revisão de erros**: lista de erros (seus por padrão, com opção de
   incluir os do adversário), filtrável por nível, tema, categoria; ao
   clicar: posição, o que foi jogado, a refutação, a linha da engine,
   puzzles gerados a partir dela. Seção de sanguessugas com "devolver à
   fila".
5. **Configurações**: usuário do chess.com, categorias importadas,
   caminho do Stockfish (com teste), profundidades, limiares, novos por
   dia, "regerar puzzles".

## 11. Testes

- **Núcleo (pytest)**:
  - Detecção de erros: função pura, casos de queda 1/2 peões, mate
    perdido, mate entregue, posição já decidida, lado correto em
    `mistake_by`.
  - SRS: cada transição da seção 8, incluindo dica = erro, atraso
    aumenta o intervalo, sanguessuga aos 5 lapsos, devolver à fila.
  - Geração de puzzles (marcados `slow`, exigem Stockfish): mate em 2
    termina no mate; dama pendurada termina na captura da dama; ganho
    vago é descartado; peão envenenado não gera; duas soluções são
    aceitas; "evitar" só com gap suficiente; temas básicos.
  - Importação: cliente com respostas gravadas (sem rede); filtro de
    categoria, dedup, retomada incremental, variante pulada.
- **API**: SQLite em memória, fluxo completo importar (mock) → analisar
  (engine mock com avaliações fixas) → fila → review → fila atualizada.
- **Frontend (vitest)**: lógica de resolução de puzzle (certo avança,
  errado desfaz e marca, dica marca, fim de relógio pergunta), com o
  tabuleiro simulado.
- **Manual**: importar as partidas reais, analisar ~20, conferir a olho
  que os puzzles fazem sentido e afinar limiares.

## 12. Fora de escopo deste ciclo

Banco de táticas do Lichess, aberturas, jogos de GMs, jogar contra a
engine, erros posicionais, multiusuário, hospedagem, FSRS, testes de
ponta a ponta no navegador.
