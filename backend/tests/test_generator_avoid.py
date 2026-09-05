import chess

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.puzzles.generator import PuzzleConfig, generate_avoid
from tests.fakes import FakeEngine, first_legal_default

CFG = PuzzleConfig(depth=10, avoid_gap_cp=150)
M = MATE_SCORE
# Posição antes do erro: brancas jogam; Nxd5 ganha a dama (o usuário jogou outra coisa na partida)
BEFORE = "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1"


def _after(fen: str, *ucis: str) -> chess.Board:
    b = chess.Board(fen)
    for u in ucis:
        b.push_uci(u)
    return b


def test_avoid_runs_the_line_to_material_gain():
    fake = FakeEngine({
        chess.Board(BEFORE).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7")), LineEval("e1e2", 0, ("e1e2",))],
        _after(BEFORE, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    d = generate_avoid(chess.Board(BEFORE), fake, CFG, played_uci="e1e2")
    assert d is not None and d.end_reason == "material_gain" and d.solver_moves == 1
    assert [m.uci for m in d.moves] == ["c3d5"] and d.explanation_pv == []


def test_avoid_not_generated_when_best_is_the_played_move():
    fake = FakeEngine({
        chess.Board(BEFORE).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7")), LineEval("e1e2", 0, ("e1e2",))],
    })
    assert generate_avoid(chess.Board(BEFORE), fake, CFG, played_uci="c3d5") is None


def test_avoid_not_generated_when_gap_is_small():
    fake = FakeEngine({
        chess.Board(BEFORE).epd(): [LineEval("c3d5", 300, ("c3d5",)), LineEval("e1e2", 200, ("e1e2",))],
    })
    assert generate_avoid(chess.Board(BEFORE), fake, CFG) is None


def test_avoid_not_generated_with_single_line():
    fake = FakeEngine({chess.Board(BEFORE).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7"))]})
    assert generate_avoid(chess.Board(BEFORE), fake, CFG) is None


def test_avoid_not_generated_without_materialization():
    # Duas linhas (gap = 400 >= avoid_gap_cp), mas a melhor nunca ganha material de fato:
    # só reis e peão andando de um lado para o outro, o "+4" nunca vira captura.
    fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
    fake = FakeEngine(
        {chess.Board(fen).epd(): [LineEval("e1d1", 400, ("e1d1", "e8d8", "d1c1", "d8c8")), LineEval("e2e3", 0, ("e2e3",))]},
        default=first_legal_default(400),
    )
    assert generate_avoid(chess.Board(fen), fake, CFG) is None


def test_avoid_mate_mode_runs_to_checkmate():
    MATE = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1"
    fake = FakeEngine({
        chess.Board(MATE).epd(): [LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8")), LineEval("a4a7", 100, ("a4a7",))],
        _after(MATE, "e1e8").epd(): [LineEval("c8e8", -(M - 1), ("c8e8",))],
        _after(MATE, "e1e8", "c8e8").epd(): [LineEval("a4e8", M - 1, ("a4e8",))],
    })
    d = generate_avoid(chess.Board(MATE), fake, CFG, played_uci="a4a7")
    assert d is not None and d.end_reason == "mate" and d.solver_moves == 2


def test_avoid_mate_mode_with_second_mate_line_is_still_infinite_gap():
    # A segunda linha também mata (mate-in-4, M-4), só que mais devagar: a diferença numérica
    # entre M-2 e M-4 é minúscula perto de avoid_gap_cp, mas mate a favor no melhor lance
    # continua valendo gap infinito -- não pode ser descartado como "gap pequeno".
    MATE = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1"
    fake = FakeEngine({
        chess.Board(MATE).epd(): [LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8")), LineEval("e1e7", M - 4, ("e1e7",))],
        _after(MATE, "e1e8").epd(): [LineEval("c8e8", -(M - 1), ("c8e8",))],
        _after(MATE, "e1e8", "c8e8").epd(): [LineEval("a4e8", M - 1, ("a4e8",))],
    })
    d = generate_avoid(chess.Board(MATE), fake, CFG, played_uci="a4a7")
    assert d is not None and d.end_reason == "mate" and d.solver_moves == 2
