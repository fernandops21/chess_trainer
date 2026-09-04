import json
from dataclasses import asdict, dataclass, field

import chess

from chess_trainer.core.analysis.engine import EngineLike, LineEval
from chess_trainer.core.evals import clamp, is_mate_for
from chess_trainer.core.puzzles.material import floor_to_piece, material_balance


@dataclass
class SolutionMove:
    uci: str
    by: str  # "solver" | "engine"
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PuzzleDraft:
    fen_start: str
    side_to_move: str
    moves: list[SolutionMove]
    end_reason: str  # "mate" | "material_gain" | "explanation"
    solver_moves: int
    explanation_pv: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({"moves": [m.to_dict() for m in self.moves], "explanation_pv": self.explanation_pv})


@dataclass(frozen=True)
class PuzzleConfig:
    depth: int = 22
    alt_window_cp: int = 50
    max_solver_moves: int = 10
    max_mate_moves: int = 15
    min_solver_eval_cp: int = 100
    avoid_gap_cp: int = 150


def _color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


def _gain(board: chess.Board, solver: chess.Color, start_balance: int) -> int:
    return material_balance(board, solver) - start_balance


def _is_close(best: LineEval, alt: LineEval, cfg: PuzzleConfig, mate_mode: bool) -> bool:
    if mate_mode:
        return alt.score == best.score
    return best.score - alt.score <= cfg.alt_window_cp


def _final_alternatives(
    board: chess.Board, close_alts: list[LineEval], mate_mode: bool,
    target: int, start_balance: int, solver: chess.Color,
) -> list[str] | None:
    """Alternativas aceitas no lance final; None se alguma alternativa próxima não materializa."""
    accepted: list[str] = []
    for alt in close_alts:
        b = board.copy()
        b.push_uci(alt.move)
        if b.is_checkmate():
            accepted.append(alt.move)
            continue
        if mate_mode:
            return None
        gain_now = _gain(b, solver, start_balance)
        if len(alt.pv) > 1:
            b.push_uci(alt.pv[1])
        gain_after = _gain(b, solver, start_balance)
        if gain_now >= target and gain_after >= target:
            accepted.append(alt.move)
        else:
            return None
    return accepted


def _draft(board: chess.Board, moves: list[SolutionMove], end_reason: str) -> PuzzleDraft:
    return PuzzleDraft(
        fen_start=board.fen(),
        side_to_move=_color_name(board.turn),
        moves=moves,
        end_reason=end_reason,
        solver_moves=sum(1 for m in moves if m.by == "solver"),
    )


def generate_punish(board: chess.Board, drop_cp: int, engine: EngineLike, cfg: PuzzleConfig) -> PuzzleDraft | None:
    solver = board.turn
    start_balance = material_balance(board, solver)

    lines: list[LineEval] | None = engine.analyse(board, cfg.depth, multipv=3)
    if not lines:
        return None
    mate_mode = is_mate_for(lines[0].score)
    target = 0
    if not mate_mode:
        if lines[0].score < cfg.min_solver_eval_cp:
            return None
        target = floor_to_piece(clamp(drop_cp) / 100)
        if target <= 0:
            return None

    limit = cfg.max_mate_moves if mate_mode else cfg.max_solver_moves
    moves: list[SolutionMove] = []
    current = board.copy()

    for _ in range(limit):
        if lines is None:
            lines = engine.analyse(current, cfg.depth, multipv=3)
            if not lines:
                return None
        best = lines[0]
        close_alts = [alt for alt in lines[1:] if _is_close(best, alt, cfg, mate_mode)]

        after = current.copy()
        after.push_uci(best.move)
        if after.is_checkmate():
            alts = _final_alternatives(current, close_alts, mate_mode, target, start_balance, solver)
            if alts is None:
                return None
            moves.append(SolutionMove(best.move, "solver", alts))
            return _draft(board, moves, "mate")

        reply_lines = engine.analyse(after, cfg.depth, multipv=1)
        if not reply_lines:
            return None
        reply = reply_lines[0]
        after_reply = after.copy()
        after_reply.push_uci(reply.move)

        if not mate_mode and _gain(after, solver, start_balance) >= target \
                and _gain(after_reply, solver, start_balance) >= target:
            alts = _final_alternatives(current, close_alts, mate_mode, target, start_balance, solver)
            if alts is None:
                return None
            moves.append(SolutionMove(best.move, "solver", alts))
            return _draft(board, moves, "material_gain")

        if close_alts:
            return None  # ambiguidade em lance intermediário

        moves.append(SolutionMove(best.move, "solver"))
        moves.append(SolutionMove(reply.move, "engine"))
        current = after_reply
        if current.is_game_over():
            return None
        lines = None

    return None
