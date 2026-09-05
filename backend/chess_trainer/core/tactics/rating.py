RATING_FLOOR = 400
RATING_CEIL = 3200


def elo_update(user: int, puzzle: int, success: bool, k: int = 32) -> int:
    """Elo simplificado: o puzzle é o adversário; acerto sem dica = vitória."""
    expected = 1.0 / (1.0 + 10 ** ((puzzle - user) / 400.0))
    score = 1.0 if success else 0.0
    updated = round(user + k * (score - expected))
    return max(RATING_FLOOR, min(RATING_CEIL, updated))
