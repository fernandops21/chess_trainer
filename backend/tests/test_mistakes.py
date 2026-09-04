import pytest

from chess_trainer.config import AppSettings, thresholds_from
from chess_trainer.core.analysis.game_analyzer import PositionData
from chess_trainer.core.analysis.mistakes import Thresholds, classify_move, classify_positions, mover_color
from chess_trainer.core.evals import MATE_SCORE

T = Thresholds()
M = MATE_SCORE


@pytest.mark.parametrize("before,after,expected", [
    (50, -180, "blunder"),          # queda 230
    (50, -100, "mistake"),          # queda 150
    (50, -20, None),                # queda 70
    (50, 60, None),                 # melhorou
    (M - 3, 300, "blunder"),        # perdeu mate
    (M - 3, M - 5, None),           # mate continua
    (100, -(M - 4), "blunder"),     # entregou mate
    (-(M - 4), -(M - 2), None),     # já estava mateado
    (1500, 1100, None),             # decidido dos dois lados
    (-1500, -1900, None),           # perdido dos dois lados
    (1500, 900, "blunder"),         # saiu da zona decidida
    (M - 2, 1200, "blunder"),       # perdeu mate mesmo ficando na zona decidida
    (1200, -(M - 3), "blunder"),    # entregou mate a partir da zona decidida
    (0, -100, "mistake"),           # queda exatamente no limiar de mistake
    (0, -200, "blunder"),           # queda exatamente no limiar de blunder
    (0, -99, None),                 # um abaixo do limiar
    (1000, 1000, None),             # exatamente na borda decidida, dos dois lados
    (1000, 700, "blunder"),         # na borda antes, saiu depois
    (-1000, -1300, None),           # perdido dos dois lados, na borda
])
def test_classify_move(before, after, expected):
    assert classify_move(before, after, T) == expected


def test_custom_thresholds():
    t = Thresholds(mistake_cp=50, blunder_cp=300)
    assert classify_move(0, -60, t) == "mistake"
    assert classify_move(0, -250, t) == "mistake"
    assert classify_move(0, -310, t) == "blunder"


def test_mover_color():
    assert mover_color(1) == "white" and mover_color(2) == "black" and mover_color(7) == "white"


def _pd(ply, before, after):
    return PositionData(ply=ply, fen="f", move_played="x", move_uci="a1a2",
                        eval_before=before, eval_after=after, best_move=None, best_eval=before)


def test_classify_positions_sets_fields_and_side():
    positions = [_pd(1, 20, 10), _pd(2, -10, -300), _pd(3, 300, 50)]
    n = classify_positions(positions, my_color="black", t=T)
    assert n == 2
    assert positions[0].is_mistake is False and positions[0].mistake_level is None
    assert positions[1].mistake_level == "blunder" and positions[1].mistake_by == "me"
    assert positions[2].mistake_level == "blunder" and positions[2].mistake_by == "opponent"


def test_thresholds_from_settings():
    t = thresholds_from(AppSettings(mistake_threshold_cp=80, blunder_threshold_cp=250))
    assert t == Thresholds(mistake_cp=80, blunder_cp=250, decided_cp=1000)
