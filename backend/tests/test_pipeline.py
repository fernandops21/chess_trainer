import chess
from sqlalchemy import func, select

from chess_trainer.config import AppSettings
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import Game, Position, Puzzle, Review
from chess_trainer.core.pipeline import analyze_pending
from chess_trainer.core.puzzles.service import regenerate_all
from tests.fakes import FakeEngine, first_legal_default
from tests.test_models import _game

SCHOLAR = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"
SETTINGS = AppSettings(analysis_depth=6, puzzle_depth=8)


def _before_mate() -> chess.Board:
    b = chess.Board()
    for u in ("e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6"):
        b.push_uci(u)
    return b


def _engine() -> FakeEngine:
    return FakeEngine(
        {_before_mate().epd(): [LineEval("h5f7", MATE_SCORE - 1, ("h5f7",))]},
        first_legal_default(0),
    )


def test_analyze_pending_classifies_and_generates_puzzle(db_session):
    game = _game(pgn=SCHOLAR, my_color="white")
    db_session.add(game)
    db_session.commit()
    events = []

    n = analyze_pending(db_session, _engine(), SETTINGS, progress=lambda *a: events.append(a))

    assert n == 1
    assert game.analyzed_at is not None and game.analysis_depth == 6
    positions = db_session.scalars(select(Position).order_by(Position.ply)).all()
    assert len(positions) == 7
    mistakes = [p for p in positions if p.is_mistake]
    assert [(p.ply, p.mistake_level, p.mistake_by) for p in mistakes] == [(6, "blunder", "opponent")]
    puzzles = db_session.scalars(select(Puzzle)).all()
    assert len(puzzles) == 1
    pz = puzzles[0]
    assert pz.kind == "punish" and pz.theme == "mate_in_1" and pz.category == "rapid"
    assert pz.side_to_move == "white" and pz.solver_moves == 1 and pz.end_reason == "mate"
    assert pz.solution_data["moves"][0]["uci"] == "h5f7"
    assert pz.position_id == mistakes[0].id and pz.game_id == game.id
    assert events[0][0] == "analyze" and events[0][2] == 1


def test_analyze_pending_skips_already_analyzed_and_respects_limit(db_session):
    db_session.add_all([_game(source_id="g1", pgn=SCHOLAR), _game(source_id="g2", pgn=SCHOLAR)])
    db_session.commit()
    assert analyze_pending(db_session, _engine(), SETTINGS, limit=1) == 1
    assert analyze_pending(db_session, _engine(), SETTINGS) == 1
    assert analyze_pending(db_session, _engine(), SETTINGS) == 0
    # dedup por fen_start + kind: as duas partidas iguais geram um puzzle só
    assert db_session.scalar(select(func.count(Puzzle.id))) == 1


def test_engine_crash_skips_game_without_raising(db_session):
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    engine = _engine()
    engine.fail_next = True
    assert analyze_pending(db_session, engine, SETTINGS) == 0
    assert game.analyzed_at is None
    assert analyze_pending(db_session, engine, SETTINGS) == 1


def test_pgn_without_moves_is_marked_analyzed(db_session):
    game = _game(pgn='[Event "x"]\n\n*')
    db_session.add(game)
    db_session.commit()
    assert analyze_pending(db_session, _engine(), SETTINGS) == 1
    assert game.analyzed_at is not None and game.analysis_depth == 0
    assert db_session.scalar(select(func.count(Position.id))) == 0


def test_regenerate_all_drops_reviews_and_rebuilds(db_session):
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)
    old = db_session.scalars(select(Puzzle)).one()
    db_session.add(Review(puzzle_id=old.id, result="correct", ease=2.5, interval_days=1,
                          due_at=old.created_at, lapses=0))
    db_session.commit()

    n = regenerate_all(db_session, _engine(), SETTINGS)

    assert n == 1
    assert db_session.scalar(select(func.count(Review.id))) == 0
    new = db_session.scalars(select(Puzzle)).one()
    assert new.id != old.id and new.theme == "mate_in_1"


def test_analyze_pending_by_game_id(db_session):
    g1 = _game(source_id="g1", pgn=SCHOLAR)
    g2 = _game(source_id="g2", pgn=SCHOLAR)
    db_session.add_all([g1, g2])
    db_session.commit()
    assert analyze_pending(db_session, _engine(), SETTINGS, game_id=g2.id) == 1
    assert g2.analyzed_at is not None and g1.analyzed_at is None
    assert analyze_pending(db_session, _engine(), SETTINGS, game_id=g2.id) == 0  # já analisada


def test_regenerate_all_survives_engine_crash(db_session):
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)

    engine = _engine()
    engine.fail_next = True
    assert regenerate_all(db_session, engine, SETTINGS) == 0
    assert db_session.scalar(select(func.count(Puzzle.id))) == 0

    assert regenerate_all(db_session, engine, SETTINGS) == 1
    assert db_session.scalar(select(func.count(Puzzle.id))) == 1


class _CountingEngine(FakeEngine):
    """Conta chamadas com multipv=3 (fase de puzzles, geracao de 'punir')."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.multipv3_calls = 0

    def analyse(self, board, depth, multipv=1):
        lines = super().analyse(board, depth, multipv)
        if multipv == 3:
            self.multipv3_calls += 1
        return lines


def test_analyze_pending_cancels_mid_game_without_persisting(db_session):
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    engine = _CountingEngine(
        {_before_mate().epd(): [LineEval("h5f7", MATE_SCORE - 1, ("h5f7",))]},
        first_legal_default(0),
    )
    should_stop = lambda: engine.multipv3_calls >= 1  # noqa: E731

    n = analyze_pending(db_session, engine, SETTINGS, should_stop=should_stop)

    assert n == 0
    assert game.analyzed_at is None
    assert db_session.scalar(select(func.count(Position.id))) == 0
    assert db_session.scalar(select(func.count(Puzzle.id))) == 0


def test_regenerate_all_cancels_mid_game_without_committing(db_session):
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)
    before = db_session.scalar(select(func.count(Puzzle.id)))
    assert before == 1

    engine = _CountingEngine(
        {_before_mate().epd(): [LineEval("h5f7", MATE_SCORE - 1, ("h5f7",))]},
        first_legal_default(0),
    )
    should_stop = lambda: engine.multipv3_calls >= 1  # noqa: E731

    n = regenerate_all(db_session, engine, SETTINGS, should_stop=should_stop)

    assert n == 0
    # deleção de Puzzle/Review antes do laço é commitada; a partida cancelada não é recriada
    assert db_session.scalar(select(func.count(Puzzle.id))) == 0


def test_analyze_pending_stops_when_asked(db_session):
    db_session.add_all([_game(source_id="g1", pgn=SCHOLAR), _game(source_id="g2", pgn=SCHOLAR)])
    db_session.commit()

    # baseado em estado real (partidas já commitadas), não em contagem de chamadas: agora
    # should_stop também é checado dentro de draft_puzzles (item 5), então uma partida pode
    # chamá-lo mais de uma vez antes de terminar.
    def should_stop() -> bool:
        return db_session.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_not(None))) >= 1

    assert analyze_pending(db_session, _engine(), SETTINGS, should_stop=should_stop) == 1
    assert db_session.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_not(None))) == 1
