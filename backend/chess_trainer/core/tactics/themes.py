"""Temas do banco do Lichess: tradução e prioridade para escolher o tema principal."""

THEME_LABELS: dict[str, str] = {
    "fork": "garfo", "pin": "cravada", "skewer": "espeto", "discoveredAttack": "ataque descoberto",
    "doubleCheck": "xeque duplo", "hangingPiece": "peça pendurada", "trappedPiece": "peça presa",
    "deflection": "desvio", "attraction": "atração", "clearance": "limpeza", "interference": "interferência",
    "intermezzo": "lance intermediário", "sacrifice": "sacrifício", "xRayAttack": "raio X",
    "capturingDefender": "captura do defensor", "backRankMate": "mate na última fileira",
    "smotheredMate": "mate sufocado", "anastasiaMate": "mate de Anastasia", "arabianMate": "mate árabe",
    "bodenMate": "mate de Boden", "doubleBishopMate": "mate dos dois bispos", "dovetailMate": "mate cauda de andorinha",
    "hookMate": "mate do gancho", "killBoxMate": "mate da caixa", "vukovicMate": "mate de Vukovic",
    "promotion": "promoção", "underPromotion": "subpromoção", "advancedPawn": "peão avançado",
    "exposedKing": "rei exposto", "kingsideAttack": "ataque na ala do rei", "queensideAttack": "ataque na ala da dama",
    "attackingF2F7": "ataque a f2/f7", "quietMove": "lance quieto", "defensiveMove": "lance defensivo",
    "zugzwang": "zugzwang", "enPassant": "en passant", "castling": "roque",
    "mateIn1": "mate em 1", "mateIn2": "mate em 2", "mateIn3": "mate em 3", "mateIn4": "mate em 4", "mateIn5": "mate em 5",
    "mate": "mate", "crushing": "esmagador", "advantage": "vantagem", "equality": "igualdade",
    "opening": "abertura", "middlegame": "meio-jogo", "endgame": "final",
    "pawnEndgame": "final de peões", "rookEndgame": "final de torres", "bishopEndgame": "final de bispos",
    "knightEndgame": "final de cavalos", "queenEndgame": "final de damas", "queenRookEndgame": "final de dama e torre",
    "oneMove": "um lance", "short": "curto", "long": "longo", "veryLong": "muito longo",
    "master": "partida de mestre", "masterVsMaster": "mestre contra mestre", "superGM": "super GM",
    "tactic": "tática",
}

# ordem de preferência para o tema principal: motivos táticos antes de mates
# nomeados, mates antes de fase/duração. Tudo que está aqui tem rótulo.
THEME_PRIORITY: list[str] = [
    "fork", "pin", "skewer", "discoveredAttack", "doubleCheck", "hangingPiece", "trappedPiece",
    "deflection", "attraction", "clearance", "interference", "intermezzo", "sacrifice", "xRayAttack",
    "capturingDefender", "backRankMate", "smotheredMate", "anastasiaMate", "arabianMate", "bodenMate",
    "doubleBishopMate", "dovetailMate", "hookMate", "killBoxMate", "vukovicMate", "promotion", "underPromotion",
    "advancedPawn", "exposedKing", "kingsideAttack", "queensideAttack", "attackingF2F7", "quietMove",
    "defensiveMove", "zugzwang", "enPassant", "castling", "mateIn1", "mateIn2", "mateIn3", "mateIn4", "mateIn5",
    "mate", "pawnEndgame", "rookEndgame", "bishopEndgame", "knightEndgame", "queenEndgame", "queenRookEndgame",
    "opening", "middlegame", "endgame",
]

# temas dos puzzles próprios (core/puzzles/themes.py) com equivalente no Lichess
OWN_THEME_TO_LICHESS: dict[str, str] = {
    "fork": "fork", "pin": "pin", "discovered_attack": "discoveredAttack", "hanging_piece": "hangingPiece",
    "tactic": "tactic",
}

_RANK = {t: i for i, t in enumerate(THEME_PRIORITY)}


def primary_theme(themes: list[str]) -> str:
    ranked = sorted((t for t in themes if t in _RANK), key=_RANK.__getitem__)
    if ranked:
        return ranked[0]
    return themes[0] if themes else "tactic"


def normalize_own_theme(theme: str) -> str:
    """Tema de um puzzle próprio → nome do Lichess (mate_in_N → mateInN)."""
    if theme.startswith("mate_in_"):
        n = theme[8:]
        return f"mateIn{n}" if n.isdigit() and int(n) <= 5 else "mate"
    return OWN_THEME_TO_LICHESS.get(theme, theme)
