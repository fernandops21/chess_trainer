# Chess Trainer — backend

## Rodar

    cd backend
    uv sync
    uv run python -m chess_trainer

API em http://127.0.0.1:8000, documentação interativa em /docs.

Por padrão o servidor escuta em `0.0.0.0:8000` (acessível de outros dispositivos na mesma rede,
como o celular); defina `CHESS_TRAINER_HOST=127.0.0.1` para restringir ao próprio computador.
Se existir `frontend/dist` (gerado por `npm run build`), ele é servido em `/`.

## Stockfish

Baixe o binário em https://stockfishchess.org/download/ (Windows: `stockfish-windows-x86-64-avx2.zip`)
e extraia em `backend/engines/`. O app encontra `engines/**/stockfish*.exe` sozinho; ou informe o
caminho em `PUT /api/settings {"stockfish_path": "..."}`.

## Táticas do Lichess

Banco público de táticas (https://database.lichess.org/#puzzles, CC0). Rotas:

    GET  /api/tactics/status          # importado?, contagem, data, rating atual, tentativas
    POST /api/tactics/import          # 202: enfileira o job "import_lichess" (baixa + importa)
    GET  /api/tactics/next            # próxima tática; ?themes=fork,pin&exclude=id1,id2
    POST /api/tactics/attempts        # registra a tentativa e atualiza o rating (Elo)
    GET  /api/tactics/themes          # temas disponíveis com a contagem (em cache)
    GET  /api/stats/themes?days=30    # acerto por tema no período (táticas + puzzles próprios)

O job baixa `lichess_db_puzzle.csv.zst` (~300 MB) para `backend/data/`, filtra por
`lichess_min_plays`/`lichess_min_popularity` (configurações) e grava em lotes; o cancelamento é
respeitado entre os lotes e no download. Se o arquivo já estiver em `backend/data/` com o mesmo tamanho
do remoto, o download é pulado; importar de novo não duplica (INSERT OR IGNORE), então dá para retomar
uma importação cancelada.

`CHESS_TRAINER_LICHESS_SOURCE` define a origem: um **caminho local** para um `.csv.zst` já baixado
(útil em testes e para reimportar sem rede) ou uma **URL**. O padrão é
`https://database.lichess.org/lichess_db_puzzle.csv.zst`.

## Estudos

Capítulos de estudos viram exercícios (`source = "study"`). Um estudo pode vir do Lichess
(`origin = "lichess"`) ou ser feito aqui no editor (`origin = "local"`). Rotas:

    GET    /api/studies                  # estudos com capítulos, quantos na repetição e vencidos hoje
    GET    /api/studies/{id}             # detalhe: capítulos em ordem, modo, puzzle_id, enunciado
    POST   /api/studies/import           # 202: enfileira o job "import_study"; corpo {"url": ...} ou {"pgn": ...}
    POST   /api/studies/{id}/reimport    # 202: baixa de novo pelo lichess_id guardado
    POST   /api/studies/{id}/queue       # {"in_queue": bool} para todos os capítulos do estudo
    DELETE /api/studies/{id}             # 204: apaga estudo, capítulos, puzzles e histórico

    POST   /api/studies                  # 201: estudo local vazio; corpo {title, author}
    PUT    /api/studies/{id}             # {title?, author?, chapter_order?}; ordem incompleta dá 400
    GET    /api/studies/{id}/pgn         # PGN do estudo inteiro, como download
    GET    /api/studies/{id}/chapters/{cid}            # capítulo completo: fen, orientation, tree, pgn
    POST   /api/studies/{id}/chapters                  # 201: capítulo novo; corpo {name, fen?, orientation?, mode?}
    PUT    /api/studies/{id}/chapters/{cid}            # salva {name, mode, orientation, tree}; árvore inválida dá 422
    DELETE /api/studies/{id}/chapters/{cid}            # 204: capítulo, exercício e revisões dele
    POST   /api/studies/{id}/chapters/{cid}/duplicate  # 201: cópia logo depois, como leitura
    GET    /api/studies/{id}/chapters/{cid}/pgn        # PGN de um capítulo, como download

O job `import_study` baixa `https://lichess.org/api/study/{id}.pgn` (redirecionamentos seguidos,
timeout de 30 s) ou usa o PGN colado, separa os capítulos com python-chess e faz o upsert pela chave
`lichess_url` do capítulo — reimportar atualiza a linha e mantém o id e o histórico do exercício.
Progresso: `"i/total capítulos"`; mensagem final: `"N capítulos, M exercícios, K pulados[: nomes]"`.
Estudo privado ou inexistente (404 do Lichess) termina o job em `error` com
`"estudo privado ou inexistente; exporte o PGN no Lichess e cole aqui"`.

`create_app(study_http_factory=...)` troca o cliente HTTP usado no download (o padrão é
`httpx.Client(follow_redirects=True, timeout=30.0)`); os testes passam um `httpx.MockTransport` por
ali, sem rede.

### Editor

A árvore de lances (`core/studies/tree.py`, gravada em `study_chapters.tree_json`) é a fonte da
verdade do capítulo: ao salvar, dela saem o PGN, a FEN, a orientação, o enunciado e o exercício.
O exercício é recriado pelas mesmas regras da reimportação — o id e o histórico da repetição
espaçada continuam os mesmos, mesmo quando a linha principal muda. Capítulo em modo `read` (ou
`gamebook` ainda sem lances) não tem exercício: o que havia sai da fila, sem ser apagado; voltar
para `gamebook` o devolve à fila.

Validação do servidor (mensagens em português na lista `detail` do 422): FEN válida, todos os
lances legais, no máximo 2 000 lances por capítulo e comentários de até 4 000 caracteres.

Duplicar um capítulo copia a árvore, mas a cópia entra como leitura: ela começa na mesma posição
do original e a única `(fen_start, kind, source)` não deixa dois exercícios de estudo partirem da
mesma FEN. Quem duplicou muda a posição (ou a linha) e escolhe `gamebook` ao salvar a cópia.

Exportar dá o PGN no formato que o Lichess importa (um jogo por capítulo, com `[StudyName]`,
`[ChapterName]`, `[ChapterMode]`, `[Orientation]`, `[FEN]`/`[SetUp]`, `[%cal]`/`[%csl]` e NAGs).
Exportar um estudo e importá-lo de volta devolve exatamente as mesmas árvores.

## Atualização do banco

O esquema de `puzzles` mudou nesta versão (`position_id`/`game_id` passaram a aceitar nulo, para
exercícios que não vêm de uma partida). Na primeira vez que o servidor sobe, a migração faz uma **cópia
do arquivo do banco** ao lado dele (`backend/data/chess_trainer.db.bak-<AAAAMMDD-HHMMSS>`) e reconstrói a
tabela copiando todas as linhas — nenhum puzzle e nenhuma revisão se perde. Confira que está tudo certo
e apague a cópia quando quiser.

## Testes

    uv run pytest -q            # rápidos
    uv run pytest -q -m slow    # com Stockfish real

## Primeiro uso

1. `PUT /api/settings` com `{"chesscom_username": "seu-usuario"}`
2. `POST /api/import` e acompanhe em `GET /api/status`
3. `POST /api/analyze?limit=5` (depth 18 leva ~20 s por partida)
4. `GET /api/queue` devolve os puzzles do dia
