import threading
from collections import OrderedDict
from typing import Callable

import chess
import chess.engine

from chess_trainer.core.analysis.engine import EngineLike


class InteractiveAnalyzer:
    """Analisador interativo para o tabuleiro de análise do frontend.

    Mantém uma engine própria (separada da usada pelos jobs em background),
    criada de forma preguiçosa na primeira chamada, protegida por um lock
    (uma análise por vez) e com um cache LRU em memória por ``(fen, multipv)``
    para que voltar/avançar entre posições já vistas não espere a engine.
    """

    def __init__(
        self,
        engine_factory: Callable[[], EngineLike | None],
        depth: int = 16,
        max_seconds: float = 3.0,
        cache_size: int = 500,
    ):
        self._factory = engine_factory
        self._engine: EngineLike | None = None
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple[str, int], dict] = OrderedDict()
        self.depth, self.max_seconds, self.cache_size = depth, max_seconds, cache_size

    def _ensure_engine(self) -> EngineLike:
        if self._engine is None:
            self._engine = self._factory()
            if self._engine is None:
                raise RuntimeError("engine indisponível")
        return self._engine

    @staticmethod
    def _terminal(board: chess.Board) -> str | None:
        if board.is_checkmate():
            return "checkmate"
        if board.is_stalemate():
            return "stalemate"
        if board.is_game_over():
            return "draw"
        return None

    def analyse(self, fen: str, multipv: int = 3) -> dict:
        board = chess.Board(fen)  # ValueError se inválido
        key = (board.fen(), multipv)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            result = {
                "fen": board.fen(),
                "turn": "white" if board.turn else "black",
                "terminal": self._terminal(board),
                "lines": [],
            }
            if result["terminal"] is None:
                engine = self._ensure_engine()
                try:
                    lines = engine.analyse(board, self.depth, multipv=multipv, max_seconds=self.max_seconds)
                except chess.engine.EngineError:
                    # engine morta: fecha e descarta para não reusar um processo quebrado na
                    # próxima chamada (que vai recriar via _ensure_engine)
                    engine.close()
                    self._engine = None
                    raise
                for line in lines:
                    b = board.copy()
                    pv_san: list[str] = []
                    for uci in line.pv:
                        mv = chess.Move.from_uci(uci)
                        if mv not in b.legal_moves:
                            break
                        pv_san.append(b.san(mv))
                        b.push(mv)
                    result["lines"].append({
                        "move": line.move,
                        "san": pv_san[0] if pv_san else line.move,
                        "score": line.score,
                        "pv": list(line.pv),
                        "pv_san": pv_san,
                    })
            self._cache[key] = result
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return result

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close()
            self._engine = None
