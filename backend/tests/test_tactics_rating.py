from chess_trainer.core.tactics.rating import elo_update


def test_equal_ratings_win_gives_plus_16():
    assert elo_update(1200, 1200, True) == 1216


def test_equal_ratings_loss_gives_minus_16():
    assert elo_update(1200, 1200, False) == 1184


def test_beating_much_stronger_puzzle_gives_more():
    assert elo_update(1200, 1600, True) > elo_update(1200, 1000, True)


def test_never_below_floor():
    # derrota surpreendente (usuário bem mais forte que o puzzle) deve travar no piso
    assert elo_update(410, 100, False) == 400
