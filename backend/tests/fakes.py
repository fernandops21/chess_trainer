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
