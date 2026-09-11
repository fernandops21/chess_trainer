import hashlib
from typing import Callable

import chess

from chess_trainer.core.analysis.engine import LineEval


def first_legal_default(score: int) -> Callable[[chess.Board], list[LineEval]]:
    def _default(board: chess.Board) -> list[LineEval]:
        legal = list(board.legal_moves)
        if not legal:
            return []
        quiet = [m for m in legal if not board.is_capture(m)]
        move = (quiet or legal)[0].uci()
        return [LineEval(move, score, (move,))]

    return _default


class FakeEngine:
    def __init__(self, script: dict[str, list[LineEval]] | None = None, default=None):
        self.script = script or {}
        self.default = default
        self.calls: list[str] = []
        self.depths: list[int] = []
        self.multipvs: list[int] = []
        self.max_seconds: list[float | None] = []
        self.fail_next = False  # simula engine morta na próxima chamada

    def analyse(
        self, board: chess.Board, depth: int, multipv: int = 1, max_seconds: float | None = None,
    ) -> list[LineEval]:
        if self.fail_next:
            self.fail_next = False
            import chess.engine
            raise chess.engine.EngineTerminatedError("engine morreu")
        key = board.epd()
        self.calls.append(key)
        self.depths.append(depth)
        self.multipvs.append(multipv)
        self.max_seconds.append(max_seconds)
        if key in self.script:
            return self.script[key][:multipv]
        if self.default is not None:
            return self.default(board)[:multipv]
        raise KeyError(f"posição sem script: {key}")

    def close(self) -> None:
        pass

    def restart(self) -> None:
        pass


class EmbeddingsFalso:
    """Vetores determinísticos por saco de palavras: textos que compartilham palavras ficam perto.

    A dimensão precisa ser folgada (64) para a propriedade valer: com poucos
    baldes, palavras diferentes caem no mesmo e dois textos sem nenhuma palavra
    em comum acabam vizinhos."""

    def __init__(self, dim: int = 64, modelo: str = "falso"):
        self.dim = dim
        self.modelo = modelo
        self.preparado = False
        self.chamadas: list[list[str]] = []

    def preparar(self, baixar: bool = True) -> None:
        self.preparado = True

    def embed(self, textos: list[str]) -> list[list[float]]:
        self.chamadas.append(list(textos))
        out = []
        for t in textos:
            v = [0.0] * self.dim
            for palavra in t.lower().split():
                # md5 em vez de `hash`: `hash(str)` muda a cada processo (PYTHONHASHSEED)
                # e faria os vizinhos mais próximos variarem de execução para execução
                v[int(hashlib.md5(palavra.encode()).hexdigest(), 16) % self.dim] += 1.0
            out.append(v)
        return out
