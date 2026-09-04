from chess_trainer.core.puzzles.generator import SolutionMove
from chess_trainer.core.puzzles.themes import infer_theme

S = lambda uci: SolutionMove(uci, "solver")  # noqa: E731
E = lambda uci: SolutionMove(uci, "engine")  # noqa: E731


def test_mate_theme_counts_solver_moves():
    assert infer_theme("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", [S("a1a8")], "mate") == "mate_in_1"
    assert infer_theme("2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1", [S("e1e8"), E("c8e8"), S("a4e8")], "mate") == "mate_in_2"


def test_hanging_piece():
    assert infer_theme("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1", [S("c3d5")], "material_gain") == "hanging_piece"


def test_fork():
    # Nb7+ ataca rei d8 e dama a5
    assert infer_theme("3k4/8/8/q1N5/8/8/8/6K1 w - - 0 1", [S("c5b7"), E("d8c8"), S("b7a5")], "material_gain") == "fork"


def test_pin():
    # Bb5 crava o cavalo c6 no rei e8
    assert infer_theme("4k3/8/2n5/8/8/8/8/4KB2 w - - 0 1", [S("f1b5")], "material_gain") == "pin"


def test_discovered_attack():
    # Bd4+ descobre a torre e1 sobre a dama e7
    assert infer_theme("7k/4q3/8/8/8/4B3/8/4R1K1 w - - 0 1", [S("e3d4"), E("e7f6"), S("d4f6")], "material_gain") == "discovered_attack"


def test_fallback_tactic():
    assert infer_theme("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", [S("e1d1")], "material_gain") == "tactic"
    assert infer_theme("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", [], "explanation") == "tactic"
