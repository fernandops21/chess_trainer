"""Convenções de avaliação: centipawns inteiros, mate codificado como ±(MATE_SCORE - n)."""

MATE_SCORE = 100_000
MATE_THRESHOLD = 90_000
CLAMP_CP = 2_000


def is_mate_for(score: int) -> bool:
    return score >= MATE_THRESHOLD


def is_mate_against(score: int) -> bool:
    return score <= -MATE_THRESHOLD


def is_mate(score: int) -> bool:
    return abs(score) >= MATE_THRESHOLD


def mate_in(score: int) -> int | None:
    if not is_mate(score):
        return None
    return MATE_SCORE - abs(score)


def clamp(score: int) -> int:
    return max(-CLAMP_CP, min(CLAMP_CP, score))


def to_pawns(score: int) -> float:
    return clamp(score) / 100


def format_score(score: int) -> str:
    n = mate_in(score)
    if n is not None:
        return f"#{n}" if score > 0 else f"#-{n}"
    if score == 0:
        return "0.00"
    return f"{score / 100:+.2f}"
