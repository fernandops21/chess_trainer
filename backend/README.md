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

## Testes

    uv run pytest -q            # rápidos
    uv run pytest -q -m slow    # com Stockfish real

## Primeiro uso

1. `PUT /api/settings` com `{"chesscom_username": "seu-usuario"}`
2. `POST /api/import` e acompanhe em `GET /api/status`
3. `POST /api/analyze?limit=5` (depth 18 leva ~20 s por partida)
4. `GET /api/queue` devolve os puzzles do dia
