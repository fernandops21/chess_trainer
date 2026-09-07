"""Rota do livro de aberturas: proxy do explorador do Lichess com o token do usuário."""

from typing import Literal

import chess
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.config import load_settings
from chess_trainer.core.openings import OpeningsError

router = APIRouter(prefix="/api")


@router.get("/openings")
def get_openings(
    request: Request,
    fen: str = Query(..., description="posição a consultar"),
    db: Literal["masters", "lichess"] = "masters",
    session: Session = Depends(get_db),
):
    """Livro de aberturas da posição, na base de mestres ou na de jogadores."""
    try:
        chess.Board(fen)
    except ValueError as exc:
        raise HTTPException(400, "FEN inválida") from exc
    settings = load_settings(session)
    try:
        return request.app.state.openings.fetch(fen, db, settings.lichess_token)
    except OpeningsError as exc:
        raise HTTPException(exc.status, exc.message) from exc
