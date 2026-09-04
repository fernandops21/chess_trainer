import chess

from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import Position
from chess_trainer.core.puzzles.generator import PuzzleConfig
from chess_trainer.core.puzzles.service import _is_trivial_punish, build_drafts
from tests.fakes import FakeEngine, first_legal_default

CFG = PuzzleConfig(depth=10)


def _pos(**overrides) -> Position:
    defaults = dict(
        game_id="g1", ply=1, fen=chess.STARTING_FEN, move_played="e4", move_uci="e2e4",
        eval_before=0, eval_after=-50, best_move="e2e4", best_eval=0,
        is_mistake=True, mistake_level="mistake", mistake_by="opponent",
    )
    defaults.update(overrides)
    return Position(**defaults)


def test_prefilter_skips_engine_when_solver_eval_is_low():
    pos = _pos(eval_after=-50)
    fake = FakeEngine()
    drafts = build_drafts(pos, fake, CFG)
    assert drafts == []
    assert fake.calls == []


def test_prefilter_allows_engine_when_mate_for_solver():
    pos = _pos(eval_after=-(MATE_SCORE - 2))
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []


HANGING_QUEEN_FEN = "3qk3/8/8/8/8/2N5/8/4K3 b - - 0 1"  # ...Qd5?? indefesa, atacada pelo Nc3
DEFENDED_QUEEN_FEN = "3qk3/8/2p5/8/8/2N5/8/4K3 b - - 0 1"  # ...Qd5?? defendida, mas Nc3 (mais barato) ataca
HANGING_PAWN_FEN = "4k3/4p3/8/8/8/3N4/8/4K3 b - - 0 1"  # ...e5?? peão indefeso atacado pelo Nd3


def test_trivial_hanging_queen_is_not_generated():
    pos = _pos(fen=HANGING_QUEEN_FEN, move_uci="d8d5", eval_after=-900)
    fake = FakeEngine()
    assert build_drafts(pos, fake, CFG) == []
    assert fake.calls == []


def test_trivial_rule_yields_to_mate_for_solver():
    pos = _pos(fen=HANGING_QUEEN_FEN, move_uci="d8d5", eval_after=-(MATE_SCORE - 2))
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []


def test_defended_queen_with_cheap_attacker_is_trivial():
    # bound corrigido usa o ganho líquido (9-3=6 -> 800cp), não o valor de face (900cp+200);
    # com eval_after=-700 (solver +700) o ganho líquido ainda cobre a vantagem.
    pos = _pos(fen=DEFENDED_QUEEN_FEN, move_uci="d8d5", eval_after=-700)
    fake = FakeEngine()
    assert build_drafts(pos, fake, CFG) == []
    assert fake.calls == []


def test_hanging_pawn_is_not_trivial():
    pos = _pos(fen=HANGING_PAWN_FEN, move_uci="e7e5", eval_after=-300)
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []


# Achado 1: rei conta como "atacante" com PIECE_VALUES[KING] = 0, tornando qualquer peça
# defendida "trivial" por comparação (0 < valor), mesmo quando Kxsquare é ilegal.
KING_ONLY_ATTACKER_FEN = "4k3/8/2p1K3/3n4/8/8/8/8 w - - 0 1"  # Nd5 defendido por c6; só o Ke6 "ataca", mas Kxd5 é ilegal


def test_king_only_attacker_is_not_trivial():
    board_after = chess.Board(KING_ONLY_ATTACKER_FEN)
    assert not _is_trivial_punish(board_after, "c7d5", 300)


# Achado 2: atacante presa (pin) não pode capturar de fato; is_attacked_by/attackers ignoram isso.
PINNED_ATTACKER_FEN = "4k3/8/8/3qb3/8/2N5/8/K7 w - - 0 1"  # Qd5 indefesa; Nc3 preso ao Ka1 pelo Be5, Nxd5 ilegal


def test_pinned_attacker_is_not_trivial():
    board_after = chess.Board(PINNED_ATTACKER_FEN)
    assert not _is_trivial_punish(board_after, "d8d5", 300)


# Achado 4: o teto de avaliação da regra trivial deve usar o ganho líquido da captura
# (valor da peça menos o atacante mais barato quando defendida), não o valor de face.
DEFENDED_BISHOP_FEN = "3qk3/8/8/3b4/2P5/8/8/4K3 w - - 0 1"  # Bd5 defendido pela Qd8; cxd5 (peão) ataca


def test_trivial_bound_uses_net_gain_not_face_value():
    board_after = chess.Board(DEFENDED_BISHOP_FEN)
    # ganho líquido = 3 (bispo) - 1 (peão) = 2 -> teto 400cp; 500 > 400 não é trivial.
    assert not _is_trivial_punish(board_after, "d7d5", 500)
    # 300 <= 400 -> trivial.
    assert _is_trivial_punish(board_after, "d7d5", 300)
