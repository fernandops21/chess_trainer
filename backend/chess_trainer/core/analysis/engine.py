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
    def analyse(self, board: chess.Board, depth: int, multipv: int = 1) -> list[LineEval]: ...


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

    def analyse(self, board: chess.Board, depth: int, multipv: int = 1) -> list[LineEval]:
        if board.is_game_over() or self._engine is None:
            return []
        infos = self._engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
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
            except chess.engine.EngineError:
                pass
            self._engine = None

    def restart(self) -> None:
        self.close()
        self._open()


def find_stockfish(configured: str) -> str | None:
    if configured and Path(configured).is_file():
        return configured
    on_path = shutil.which("stockfish")
    if on_path:
        return on_path
    root = Path(__file__).resolve().parents[3] / "engines"
    for pattern in ("**/stockfish*.exe", "**/stockfish*"):
        hits = [p for p in glob.glob(str(root / pattern), recursive=True) if os.path.isfile(p)]
        if hits:
            return sorted(hits)[0]
    return None
