# estágio 1: frontend
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# estágio 2: backend + Stockfish + frontend compilado
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends stockfish && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY --from=frontend /src/frontend/dist /app/frontend/dist
ENV CHESS_TRAINER_DATA=/data \
    CHESS_TRAINER_DB=/data/chess_trainer.db \
    STOCKFISH_PATH=/usr/games/stockfish \
    CHESS_TRAINER_HOST=0.0.0.0
VOLUME ["/data"]
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "python", "-m", "chess_trainer"]
