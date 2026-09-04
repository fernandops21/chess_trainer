from dataclasses import dataclass
from typing import Any, Iterable

from chess_trainer.core.evals import is_mate_against, is_mate_for


@dataclass(frozen=True)
class Thresholds:
    mistake_cp: int = 100
    blunder_cp: int = 200
    decided_cp: int = 1000


def classify_move(eval_before: int, eval_after: int, t: Thresholds) -> str | None:
    if is_mate_for(eval_before):
        return None if is_mate_for(eval_after) else "blunder"
    if is_mate_against(eval_before):
        return None  # já estava mateado; não há erro a marcar
    if is_mate_against(eval_after):
        return "blunder"
    if eval_before >= t.decided_cp and eval_after >= t.decided_cp:
        return None
    if eval_before <= -t.decided_cp and eval_after <= -t.decided_cp:
        return None
    drop = eval_before - eval_after
    if drop >= t.blunder_cp:
        return "blunder"
    if drop >= t.mistake_cp:
        return "mistake"
    return None


def mover_color(ply: int) -> str:
    return "white" if ply % 2 == 1 else "black"


def classify_positions(positions: Iterable[Any], my_color: str, t: Thresholds) -> int:
    count = 0
    for pos in positions:
        level = classify_move(pos.eval_before, pos.eval_after, t)
        pos.is_mistake = level is not None
        pos.mistake_level = level
        pos.mistake_by = (("me" if mover_color(pos.ply) == my_color else "opponent") if level else None)
        count += int(level is not None)
    return count
