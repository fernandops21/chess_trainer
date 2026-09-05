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

## Testes

    uv run pytest -q            # rápidos
    uv run pytest -q -m slow    # com Stockfish real

## Primeiro uso

1. `PUT /api/settings` com `{"chesscom_username": "seu-usuario"}`
2. `POST /api/import` e acompanhe em `GET /api/status`
3. `POST /api/analyze?limit=5` (depth 18 leva ~20 s por partida)
4. `GET /api/queue` devolve os puzzles do dia
