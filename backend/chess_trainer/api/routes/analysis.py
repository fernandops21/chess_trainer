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
        # cobre EngineError (subclasse de RuntimeError) e "engine sem resposta"/"engine
        # indisponível" do InteractiveAnalyzer
        raise HTTPException(503, str(exc))
    except Exception:
        # qualquer outra falha da engine: mesmo assim vira um erro visível na UI, não 500
        raise HTTPException(503, "engine falhou")
