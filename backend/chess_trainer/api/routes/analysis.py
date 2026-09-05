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
    except chess.engine.EngineError as exc:
        # precisa vir antes de RuntimeError: EngineError é subclasse de RuntimeError, e a
        # ordem inversa fazia esse except nunca ser alcançado
        raise HTTPException(503, f"engine falhou: {exc}")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
