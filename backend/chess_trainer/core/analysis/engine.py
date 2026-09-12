import asyncio
import glob
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import chess
import chess.engine

from chess_trainer.core.evals import MATE_SCORE


@dataclass(frozen=True)
class LineEval:
    move: str
    score: int
    pv: tuple[str, ...]


class EngineLike(Protocol):
    def analyse(
        self, board: chess.Board, depth: int, multipv: int = 1, max_seconds: float | None = None,
    ) -> list[LineEval]: ...
    def close(self) -> None: ...
    def restart(self) -> None: ...


def terminal_score(board: chess.Board) -> int | None:
    if board.is_checkmate():
        return -MATE_SCORE
    if board.is_game_over():
        return 0
    return None


class StockfishEngine:
    def __init__(self, path: str, threads: int = 4, hash_mb: int = 256):
        self._path = path
        self._threads = threads
        self._hash = hash_mb
        self._engine: chess.engine.SimpleEngine | None = None
        self._open()

    def _open(self) -> None:
        self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
        self._engine.configure({"Threads": self._threads, "Hash": self._hash})

    def analyse(
        self, board: chess.Board, depth: int, multipv: int = 1, max_seconds: float | None = None,
    ) -> list[LineEval]:
        """Analisa a posição com um limite de profundidade e, opcionalmente, de tempo.

        O limite efetivo de tempo é ``max_seconds`` + 10s: ``SimpleEngine`` do
        python-chess aguarda seu próprio timeout interno (10s, tempo de resposta
        do protocolo UCI) além do ``max_seconds`` configurado antes de desistir
        e levantar erro.
        """
        if board.is_game_over() or self._engine is None:
            return []
        limit = chess.engine.Limit(depth=depth, time=max_seconds)
        try:
            infos = self._engine.analyse(board, limit, multipv=multipv)
        except (TimeoutError, asyncio.TimeoutError, chess.engine.EngineTerminatedError):
            self.restart()
            raise chess.engine.EngineError(f"engine sem resposta em {max_seconds}s")
        if isinstance(infos, dict):
            infos = [infos]
        lines: list[LineEval] = []
        for info in infos:
            pv = info.get("pv")
            if not pv or "score" not in info:
                continue
            score = info["score"].pov(board.turn).score(mate_score=MATE_SCORE)
            lines.append(LineEval(pv[0].uci(), int(score), tuple(m.uci() for m in pv)))
        lines.sort(key=lambda line: line.score, reverse=True)
        return lines

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.quit()
            except (chess.engine.EngineError, TimeoutError, OSError):
                transport = getattr(self._engine, "transport", None)
                if transport is not None:
                    try:
                        transport.kill()
                    except Exception:
                        pass
            self._engine = None

    def restart(self) -> None:
        self.close()
        self._open()


def find_stockfish(configured: str) -> str | None:
    if configured and Path(configured).is_file():
        return configured
    env = os.environ.get("STOCKFISH_PATH", "")
    if env and Path(env).is_file():
        return env
    on_path = shutil.which("stockfish")
    if on_path:
        return on_path
    root = Path(__file__).resolve().parents[3] / "engines"
    for pattern in ("**/stockfish*.exe", "**/stockfish*"):
        hits = [p for p in glob.glob(str(root / pattern), recursive=True) if os.path.isfile(p)]
        if hits:
            return sorted(hits)[0]
    return None
