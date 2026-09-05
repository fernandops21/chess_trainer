import pytest

from chess_trainer.core.models import LichessPuzzle
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.themes import THEME_LABELS, primary_theme


def row(**kw) -> LichessPuzzle:
    base = dict(id="00sHx", fen="q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17",
                moves="e8d7 a2e6 d7d8 f7f8", rating=1760, rating_deviation=80, popularity=83, nb_plays=72,
                themes="mate mateIn2 middlegame short", opening_tags="")
    base.update(kw)
    return LichessPuzzle(**base)


def test_to_tactic_applies_opponent_move_and_alternates():
    t = to_tactic(row())
    # depois de e8d7 são as brancas que jogam
    assert t.side_to_move == "white"
    assert t.fen_start.split()[1] == "w"
    assert [m["uci"] for m in t.solution["moves"]] == ["a2e6", "d7d8", "f7f8"]
    assert [m["by"] for m in t.solution["moves"]] == ["solver", "engine", "solver"]
    assert all(m["alternatives"] == [] for m in t.solution["moves"])
    assert t.solver_moves == 2
    assert t.end_reason == "mate"
    assert t.theme == "mateIn2" and t.themes == ["mate", "mateIn2", "middlegame", "short"]
    assert t.lichess_url == "https://lichess.org/training/00sHx"
    assert t.rating == 1760 and t.kind == "tactic"


def test_to_tactic_material_gain_when_no_mate():
    # brancas capturam a dama com garfo de cavalo depois do lance preto
    t = to_tactic(row(id="fork1", fen="r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
                      moves="a2a3 f6e4 d2d3 e4c5", themes="fork middlegame short"))
    assert t.end_reason == "material_gain" and t.theme == "fork"


def test_to_tactic_rejects_illegal_move():
    with pytest.raises(ValueError):
        to_tactic(row(moves="e8e1 a2e6"))


def test_primary_theme_prefers_tactical_motif_over_phase():
    assert primary_theme(["middlegame", "short", "fork", "crushing"]) == "fork"
    assert primary_theme(["endgame", "long"]) == "endgame"
    assert primary_theme([]) == "tactic"


def test_every_priority_theme_has_label():
    from chess_trainer.core.tactics.themes import THEME_PRIORITY
    assert all(t in THEME_LABELS for t in THEME_PRIORITY)
