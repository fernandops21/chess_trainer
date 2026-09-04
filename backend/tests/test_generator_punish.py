import chess

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.puzzles.generator import PuzzleConfig, generate_punish
from tests.fakes import FakeEngine, first_legal_default

CFG = PuzzleConfig(depth=10)
M = MATE_SCORE


def _after(fen: str, *ucis: str) -> chess.Board:
    b = chess.Board(fen)
    for u in ucis:
        b.push_uci(u)
    return b


HANGING_QUEEN = "4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1"          # Nxd5 ganha a dama
MATE_IN_2 = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1"           # Re8+ Rxe8 Qxe8#
TWO_CAPTURES = "4k3/8/8/3q4/8/2N1N3/8/4K3 w - - 0 1"          # Nc3xd5 ou Ne3xd5
RECAPTURE = "8/8/4k3/3q4/8/8/8/3RK3 w - - 0 1"                # Rxd5 Kxd5
VAGUE = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
MATE_IN_1 = "6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1"               # Ra8#


def test_hanging_queen_ends_at_capture():
    fake = FakeEngine({
        chess.Board(HANGING_QUEEN).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7"))],
        _after(HANGING_QUEEN, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    draft = generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    assert draft.end_reason == "material_gain" and draft.solver_moves == 1
    assert [(m.uci, m.by) for m in draft.moves] == [("c3d5", "solver")]
    assert draft.side_to_move == "white" and draft.fen_start == HANGING_QUEEN
    assert len(fake.calls) == 2


def test_mate_in_two_runs_to_checkmate():
    fake = FakeEngine({
        chess.Board(MATE_IN_2).epd(): [LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8"))],
        _after(MATE_IN_2, "e1e8").epd(): [LineEval("c8e8", -(M - 1), ("c8e8", "a4e8"))],
        _after(MATE_IN_2, "e1e8", "c8e8").epd(): [LineEval("a4e8", M - 1, ("a4e8",))],
    })
    draft = generate_punish(chess.Board(MATE_IN_2), drop_cp=5000, engine=fake, cfg=CFG)
    assert draft is not None
    assert draft.end_reason == "mate" and draft.solver_moves == 2
    assert [(m.uci, m.by) for m in draft.moves] == [("e1e8", "solver"), ("c8e8", "engine"), ("a4e8", "solver")]


def test_vague_advantage_is_discarded():
    fake = FakeEngine(default=first_legal_default(150))
    assert generate_punish(chess.Board(VAGUE), drop_cp=150, engine=fake, cfg=CFG) is None


def test_two_capturing_moves_become_alternatives():
    fake = FakeEngine({
        chess.Board(TWO_CAPTURES).epd(): [
            LineEval("c3d5", 900, ("c3d5", "e8d7")),
            LineEval("e3d5", 890, ("e3d5", "e8d7")),
        ],
        _after(TWO_CAPTURES, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    draft = generate_punish(chess.Board(TWO_CAPTURES), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    assert draft.moves[0].alternatives == ["e3d5"]


def test_quiet_alternative_within_window_discards():
    fake = FakeEngine({
        chess.Board(HANGING_QUEEN).epd(): [
            LineEval("c3d5", 900, ("c3d5", "e8d7")),
            LineEval("e1e2", 880, ("e1e2", "e8d7")),
        ],
        _after(HANGING_QUEEN, "c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    })
    assert generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG) is None


def test_solver_not_better_is_discarded():
    fake = FakeEngine({chess.Board(HANGING_QUEEN).epd(): [LineEval("c3d5", 50, ("c3d5",))]})
    assert generate_punish(chess.Board(HANGING_QUEEN), drop_cp=300, engine=fake, cfg=CFG) is None
    assert len(fake.calls) == 1


def test_intermediate_ambiguity_discards():
    fake = FakeEngine({
        chess.Board(MATE_IN_2).epd(): [
            LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8")),
            LineEval("e1e7", M - 2, ("e1e7",)),
        ],
        _after(MATE_IN_2, "e1e8").epd(): [LineEval("c8e8", -(M - 1), ("c8e8", "a4e8"))],
    })
    assert generate_punish(chess.Board(MATE_IN_2), drop_cp=5000, engine=fake, cfg=CFG) is None


def test_gain_must_survive_best_reply():
    script = {
        chess.Board(RECAPTURE).epd(): [LineEval("d1d5", 450, ("d1d5", "e6d5"))],
        _after(RECAPTURE, "d1d5").epd(): [LineEval("e6d5", -50, ("e6d5",))],
    }
    # alvo 3 (queda 400): ganho líquido 9-5=4 sobrevive → termina em Rxd5
    draft = generate_punish(chess.Board(RECAPTURE), 400, FakeEngine(script, first_legal_default(450)), CFG)
    assert draft is not None and [m.uci for m in draft.moves] == ["d1d5"]
    # alvo 5 (queda 600): 4 < 5 → continua e, sem mais material, é descartado
    assert generate_punish(chess.Board(RECAPTURE), 600, FakeEngine(script, first_legal_default(450)), CFG) is None


def test_slower_mate_is_not_an_alternative():
    fake = FakeEngine({
        chess.Board(MATE_IN_1).epd(): [
            LineEval("a1a8", M - 1, ("a1a8",)),
            LineEval("a1a7", M - 3, ("a1a7",)),
        ],
    })
    draft = generate_punish(chess.Board(MATE_IN_1), drop_cp=5000, engine=fake, cfg=CFG)
    assert draft is not None and draft.end_reason == "mate"
    assert draft.moves[0].alternatives == []


def test_draft_json_shape():
    fake = FakeEngine({chess.Board(MATE_IN_1).epd(): [LineEval("a1a8", M - 1, ("a1a8",))]})
    draft = generate_punish(chess.Board(MATE_IN_1), drop_cp=5000, engine=fake, cfg=CFG)
    import json
    data = json.loads(draft.to_json())
    assert data == {"moves": [{"uci": "a1a8", "by": "solver", "alternatives": []}], "explanation_pv": []}
