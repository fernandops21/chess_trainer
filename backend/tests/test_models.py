import json
from datetime import datetime

from chess_trainer.core.models import Game, Position, Puzzle, Review, TrainingSession, utcnow
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, TacticsAttempt


def _game(**over):
    base = dict(
        source_id="https://www.chess.com/game/live/1",
        pgn="1. e4 e5 1-0",
        white="therealzibs",
        black="x",
        result="1-0",
        time_control="600",
        category="rapid",
        played_at=datetime(2026, 8, 1, 12, 0),
        my_color="white",
    )
    base.update(over)
    return Game(**base)


def test_utcnow_is_naive():
    assert utcnow().tzinfo is None


def test_game_defaults_and_relationships(db_session):
    game = _game()
    db_session.add(game)
    db_session.commit()
    assert len(game.id) == 36
    assert game.source == "chess.com"
    assert game.analyzed_at is None
    assert game.imported_at is not None


def test_position_puzzle_review_chain(db_session):
    game = _game()
    pos = Position(
        game=game, ply=1, fen="startfen", move_played="e4", move_uci="e2e4",
        eval_before=20, eval_after=15, best_move="e2e4", best_eval=20,
    )
    puzzle = Puzzle(
        position=pos, game=game, kind="punish", fen_start="f", side_to_move="white",
        solution=json.dumps({"moves": [{"uci": "e2e4", "by": "solver", "alternatives": []}]}),
        end_reason="material_gain", theme="tactic", category="rapid", solver_moves=1,
    )
    session = TrainingSession(planned_minutes=25, filters="{}")
    review = Review(
        puzzle=puzzle, session=session, result="correct", used_hint=False, duration_ms=1200,
        ease=2.5, interval_days=1, due_at=datetime(2026, 9, 5), lapses=0,
    )
    db_session.add_all([game, pos, puzzle, session, review])
    db_session.commit()

    assert pos.is_mistake is False and pos.mistake_level is None
    assert puzzle.is_leech is False and puzzle.srs_due_at is None and puzzle.srs_ease == 2.5
    assert puzzle.solution_data["moves"][0]["uci"] == "e2e4"
    assert game.positions[0] is pos
    assert puzzle.reviews[0] is review


def test_puzzle_unique_fen_kind(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    game = _game()
    db_session.add(game)
    for _ in range(2):
        pos = Position(game=game, ply=1, fen="f", move_played="e4", move_uci="e2e4",
                       eval_before=0, eval_after=0, best_move="e2e4", best_eval=0)
        db_session.add(Puzzle(position=pos, game=game, kind="punish", fen_start="same", side_to_move="white",
                              solution="{}", end_reason="mate", theme="tactic", category="rapid", solver_moves=1))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_lichess_puzzle_roundtrip(db_session):
    db_session.add(LichessPuzzle(id="00sHx", fen="q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17",
                                 moves="e8d7 a2e6 d7d8 f7f8", rating=1760, rating_deviation=80,
                                 popularity=83, nb_plays=72, themes="mate mateIn2 middlegame short",
                                 opening_tags=""))
    db_session.add(LichessPuzzleTheme(theme="mateIn2", puzzle_id="00sHx"))
    db_session.commit()
    row = db_session.get(LichessPuzzle, "00sHx")
    assert row.rating == 1760 and row.theme_list == ["mate", "mateIn2", "middlegame", "short"]


def test_tactics_attempt_defaults(db_session):
    db_session.add(LichessPuzzle(id="p1", fen="8/8/8/8/8/8/8/K6k w - - 0 1", moves="a1a2", rating=1000,
                                 rating_deviation=50, popularity=90, nb_plays=500, themes="endgame", opening_tags=""))
    a = TacticsAttempt(puzzle_id="p1", correct=True, used_hint=False, duration_ms=1200,
                       rating_before=1200, rating_after=1210, puzzle_rating=1000)
    db_session.add(a)
    db_session.commit()
    assert a.id and a.attempted_at is not None and a.session_id is None


def _puzzle_solto(**over) -> Puzzle:
    """Puzzle sem partida nem posição (fonte externa)."""
    base = dict(kind="punish", fen_start="fen-x", side_to_move="white", solution="{}",
                end_reason="mate", theme="tactic", category="lichess", solver_moves=1)
    base.update(over)
    return Puzzle(**base)


def test_puzzle_defaults_de_fonte(db_session):
    puzzle = _puzzle_solto(source="lichess", external_id="00sHx", fen_before="fen-antes", last_move="e8d7")
    db_session.add(puzzle)
    db_session.commit()
    assert puzzle.position_id is None and puzzle.game_id is None
    assert puzzle.in_queue is True and puzzle.chapter_id is None

    proprio = _puzzle_solto(fen_start="fen-y")
    db_session.add(proprio)
    db_session.commit()
    assert proprio.source == "own"
    assert proprio.external_id is None and proprio.fen_before is None and proprio.last_move is None


def test_puzzle_unique_fen_kind_source(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    # mesma fen e kind em fontes diferentes convivem
    db_session.add(_puzzle_solto(fen_start="mesma", source="own"))
    db_session.add(_puzzle_solto(fen_start="mesma", source="lichess"))
    db_session.commit()
    db_session.add(_puzzle_solto(fen_start="mesma", source="lichess"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_puzzle_external_id_unico_mas_aceita_varios_nulos(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    db_session.add(_puzzle_solto(fen_start="a"))
    db_session.add(_puzzle_solto(fen_start="b"))
    db_session.commit()  # dois external_id nulos convivem
    db_session.add(_puzzle_solto(fen_start="c", source="lichess", external_id="00sHx"))
    db_session.add(_puzzle_solto(fen_start="d", source="lichess", external_id="00sHx"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_study_com_capitulos_em_ordem_e_cascade(db_session):
    from chess_trainer.core.models import Study, StudyChapter
    estudo = Study(title="Aulas", author="basso", source_url="https://lichess.org/study/4JKVAfaE",
                   lichess_id="4JKVAfaE")
    db_session.add(estudo)
    db_session.flush()
    for ordem in (2, 1):
        db_session.add(StudyChapter(study_id=estudo.id, order=ordem, name=f"cap {ordem}", fen="f",
                                    orientation="white", mode="gamebook", pgn="1. e4 *",
                                    lichess_url=f"https://lichess.org/study/4JKVAfaE/c{ordem}"))
    db_session.commit()
    db_session.refresh(estudo)
    assert [c.order for c in estudo.chapters] == [1, 2]
    assert estudo.created_at is not None and estudo.imported_at is None
    assert estudo.chapters[0].in_queue is True and estudo.chapters[0].intro_comment == ""

    capitulo = estudo.chapters[0]
    puzzle = _puzzle_solto(fen_start="fen-cap", source="study", chapter_id=capitulo.id)
    db_session.add(puzzle)
    db_session.flush()
    capitulo.puzzle_id = puzzle.id
    db_session.commit()
    assert capitulo.puzzle is puzzle

    db_session.delete(estudo)
    db_session.commit()
    assert db_session.query(StudyChapter).count() == 0
