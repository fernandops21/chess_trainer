from chess_trainer.core.evals import (
    MATE_SCORE, clamp, format_score, is_mate, is_mate_against, is_mate_for, mate_in, to_pawns,
)


def test_mate_detection():
    assert is_mate_for(MATE_SCORE - 3)
    assert not is_mate_for(-(MATE_SCORE - 3))
    assert is_mate_against(-(MATE_SCORE - 1))
    assert is_mate(MATE_SCORE - 10) and is_mate(-(MATE_SCORE - 10))
    assert not is_mate(1500)


def test_mate_in():
    assert mate_in(MATE_SCORE - 2) == 2
    assert mate_in(-(MATE_SCORE - 5)) == 5
    assert mate_in(300) is None


def test_clamp_and_pawns():
    assert clamp(MATE_SCORE - 1) == 2000
    assert clamp(-5000) == -2000
    assert clamp(150) == 150
    assert to_pawns(150) == 1.5
    assert to_pawns(MATE_SCORE - 1) == 20.0


def test_format_score():
    assert format_score(MATE_SCORE - 2) == "#2"
    assert format_score(-(MATE_SCORE - 3)) == "#-3"
    assert format_score(125) == "+1.25"
    assert format_score(-40) == "-0.40"
    assert format_score(0) == "0.00"
