from fastapi import APIRouter, HTTPException, Request

from chess_trainer.api.schemas import AnalyseIn, AnalyseOut

router = APIRouter(prefix="/api")

# Tabuleiro bem formado mas impossível para a engine. O caso comum é o diagrama
# de aula sem os dois reis, que o Lichess mostra e nós também: o tabuleiro abre,
# só a análise fica de fora — a mensagem diz por quê.
POSICAO_INVALIDA = "posição inválida para a engine (faltam os dois reis ou há peças demais)"


@router.post("/analyse", response_model=AnalyseOut)
def post_analyse(body: AnalyseIn, request: Request):
    try:
        return request.app.state.analyzer.analyse(body.fen, body.multipv)
    except ValueError:
        raise HTTPException(400, POSICAO_INVALIDA)
    except RuntimeError as exc:
        # cobre EngineError (subclasse de RuntimeError) e "engine sem resposta"/"engine
        # indisponível" do InteractiveAnalyzer
        raise HTTPException(503, str(exc))
    except Exception:
        # qualquer outra falha da engine: mesmo assim vira um erro visível na UI, não 500
        raise HTTPException(503, "engine falhou")
