import chess.engine
from fastapi import APIRouter, HTTPException, Request

from chess_trainer.api.schemas import AnalyseIn, AnalyseOut

router = APIRouter(prefix="/api")


@router.post("/analyse", response_model=AnalyseOut)
def post_analyse(body: AnalyseIn, request: Request):
    try:
        return request.app.state.analyzer.analyse(body.fen, body.multipv)
    except ValueError:
        raise HTTPException(400, "FEN inválido")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except chess.engine.EngineError as exc:
        raise HTTPException(503, f"engine falhou: {exc}")
