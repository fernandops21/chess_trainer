from datetime import datetime

import chess
from sqlalchemy import func, select

from chess_trainer.config import AppSettings
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import Game, Position, Puzzle, Review, Study, StudyChapter
from chess_trainer.core.pipeline import analyze_pending
from chess_trainer.core.puzzles.service import regenerate_all, regenerate_avoid
from tests.fakes import FakeEngine, first_legal_default, no_more_lines
from tests.test_models import _game

# a partida acaba no erro do adversário (ele abandona): sem resposta do usuário no registro, o
# erro vira exercício. Com o 4.Qxf7# jogado, o usuário já teria castigado e nada seria criado.
SCHOLAR = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 1-0"
SCHOLAR_COM_O_MATE = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"
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
    assert len(positions) == 6
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

    def analyse(self, board, depth, multipv=1, max_seconds=None):
        lines = super().analyse(board, depth, multipv, max_seconds)
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


def test_regenerate_avoid_keeps_punish_and_its_reviews(db_session):
    # my_color="black": o erro do ply 6 (3...Nf6??) é MEU, então a posição antes dele é candidata a
    # "evitar" e a posição depois dele gera o "punir" (Qxf7#). Com o FakeEngine padrão a posição
    # antes de Nf6 devolve uma linha só, então nenhum "evitar" materializa (n == 0) -- o que este
    # teste garante é que a recriação dos "evitar" não toca no "punir" nem nas revisões dele.
    game = _game(pgn=SCHOLAR, my_color="black")
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)
    punish = db_session.scalars(select(Puzzle).where(Puzzle.kind == "punish")).one()
    db_session.add(Review(puzzle_id=punish.id, result="correct", ease=2.5, interval_days=1,
                          due_at=punish.created_at, lapses=0))
    db_session.commit()

    n = regenerate_avoid(db_session, _engine(), SETTINGS)

    assert db_session.scalar(select(func.count(Review.id))) == 1  # revisão do punish preservada
    assert db_session.scalar(select(Puzzle.id).where(Puzzle.kind == "punish")) == punish.id
    assert n == db_session.scalar(select(func.count(Puzzle.id)).where(Puzzle.kind == "avoid")) == 0


def test_regenerate_avoid_creates_avoid_for_my_mistake(db_session):
    # Posição sintética (dama preta pendurada em d5): brancas erraram Ke2 em vez de Nxd5,
    # que ganha a dama e se sustenta após a única resposta do rei. Monta Game/Position
    # diretamente (como tests/factories.py::make_puzzle) em vez de depender de um PGN real,
    # porque script-ar um jogo de verdade posição a posição no FakeEngine é frágil demais.
    fen = "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1"
    game = _game(pgn=SCHOLAR, my_color="white")
    game.analyzed_at = datetime(2026, 8, 1, 12, 30)
    game.analysis_depth = SETTINGS.analysis_depth
    db_session.add(game)
    db_session.flush()
    pos = Position(
        game_id=game.id, ply=1, fen=fen, move_played="Ke2", move_uci="e1e2",
        eval_before=900, eval_after=0, best_move="c3d5", best_eval=900,
        is_mistake=True, mistake_level="blunder", mistake_by="me",
    )
    db_session.add(pos)
    db_session.commit()

    def _after(*ucis: str) -> chess.Board:
        b = chess.Board(fen)
        for u in ucis:
            b.push_uci(u)
        return b

    fake = FakeEngine({
        chess.Board(fen).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7")), LineEval("e1e2", 0, ("e1e2",))],
        _after("c3d5").epd(): [LineEval("e8d7", -900, ("e8d7",))],
    }, default=no_more_lines)

    n = regenerate_avoid(db_session, fake, SETTINGS)

    assert n == 1
    puzzles = db_session.scalars(select(Puzzle).where(Puzzle.kind == "avoid")).all()
    assert len(puzzles) == 1
    pz = puzzles[0]
    assert pz.solver_moves == 1 and pz.fen_start == fen

    # segunda chamada: regenerate_avoid apaga e recria os "avoid", mas continua havendo
    # exatamente um (nunca duplica por fen_start + kind)
    n2 = regenerate_avoid(db_session, fake, SETTINGS)
    assert n2 == 1
    assert db_session.scalar(select(func.count(Puzzle.id)).where(Puzzle.kind == "avoid")) == 1


def test_regenerate_avoid_drops_old_avoid_puzzles_and_their_reviews(db_session):
    game = _game(pgn=SCHOLAR, my_color="black")
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)
    punish = db_session.scalars(select(Puzzle).where(Puzzle.kind == "punish")).one()
    stale = Puzzle(position_id=punish.position_id, game_id=game.id, kind="avoid",
                   fen_start=_before_mate().fen(), side_to_move="black",
                   solution='{"moves": [{"uci": "g8e7", "by": "solver", "alternatives": []}],'
                            ' "explanation_pv": []}',
                   end_reason="explanation", theme="tactic", category="rapid", solver_moves=1)
    db_session.add(stale)
    db_session.flush()
    db_session.add_all([
        Review(puzzle_id=punish.id, result="correct", ease=2.5, interval_days=1,
               due_at=punish.created_at, lapses=0),
        Review(puzzle_id=stale.id, result="wrong", ease=2.5, interval_days=1,
               due_at=stale.created_at, lapses=1),
    ])
    db_session.commit()

    regenerate_avoid(db_session, _engine(), SETTINGS)

    assert db_session.get(Puzzle, stale.id) is None
    reviews = db_session.scalars(select(Review)).all()
    assert [r.puzzle_id for r in reviews] == [punish.id]


def _externo(db_session, *, source: str, fen: str, chapter_id: str | None = None,
             external_id: str | None = None) -> Puzzle:
    """Exercício que não veio das partidas do usuário (tática guardada ou capítulo de estudo)."""
    puzzle = Puzzle(
        source=source, external_id=external_id, chapter_id=chapter_id, kind="punish",
        fen_start=fen, side_to_move="white",
        solution='{"moves": [{"uci": "a2a4", "by": "solver", "alternatives": []}], "explanation_pv": []}',
        end_reason="material_gain", theme=source, category=source, solver_moves=1,
    )
    db_session.add(puzzle)
    db_session.flush()
    db_session.add(Review(puzzle_id=puzzle.id, result="correct", ease=2.5, interval_days=1,
                          due_at=datetime(2026, 8, 1), lapses=0))
    return puzzle


def test_regenerate_all_keeps_tactics_and_study_exercises(db_session):
    """Recriar os puzzles só mexe nos das partidas do usuário: as táticas guardadas
    do Lichess e os exercícios dos estudos (e o histórico deles) continuam."""
    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)
    proprio = db_session.scalars(select(Puzzle).where(Puzzle.source == "own")).one()
    db_session.add(Review(puzzle_id=proprio.id, result="correct", ease=2.5, interval_days=1,
                          due_at=proprio.created_at, lapses=0))

    study = Study(title="Finais básicos")
    db_session.add(study)
    db_session.flush()
    chapter = StudyChapter(study_id=study.id, order=1, name="Oposição", fen=chess.STARTING_FEN)
    db_session.add(chapter)
    db_session.flush()
    tatica = _externo(db_session, source="lichess", external_id="abc12",
                      fen="8/8/8/8/8/5k2/6q1/7K w - - 0 1")
    estudo = _externo(db_session, source="study", chapter_id=chapter.id,
                      fen="8/8/8/8/8/4k3/6q1/7K w - - 0 1")
    chapter.puzzle_id = estudo.id
    db_session.commit()

    n = regenerate_all(db_session, _engine(), SETTINGS)

    assert n == 1
    assert db_session.get(Puzzle, tatica.id) is not None
    assert db_session.get(Puzzle, estudo.id) is not None
    assert db_session.get(Puzzle, proprio.id) is None  # o próprio foi recriado do zero
    novo = db_session.scalars(select(Puzzle).where(Puzzle.source == "own")).one()
    assert novo.id != proprio.id and novo.theme == "mate_in_1"
    # o histórico das outras fontes fica; só o do puzzle próprio sumiu
    assert sorted(r.puzzle_id for r in db_session.scalars(select(Review))) == sorted([tatica.id, estudo.id])


def test_regenerate_avoid_keeps_other_sources(db_session):
    """A recriação parcial ("evitar") também não toca nas outras fontes, mesmo que
    o exercício guardado tenha `kind` "avoid"."""
    game = _game(pgn=SCHOLAR, my_color="black")
    db_session.add(game)
    db_session.commit()
    analyze_pending(db_session, _engine(), SETTINGS)
    tatica = _externo(db_session, source="lichess", external_id="zz999",
                      fen="8/8/8/8/8/5k2/6q1/7K w - - 0 1")
    tatica.kind = "avoid"
    db_session.commit()

    regenerate_avoid(db_session, _engine(), SETTINGS)

    assert db_session.get(Puzzle, tatica.id) is not None
    assert db_session.scalar(select(func.count(Review.id)).where(Review.puzzle_id == tatica.id)) == 1


def test_lichess_puzzle_with_same_fen_does_not_suppress_own_puzzle(db_session):
    """Uma tática guardada na mesma posição inicial não pode roubar o lugar do
    exercício do próprio usuário: a única do banco é (fen_start, kind, source)."""
    guardada = _externo(db_session, source="lichess", external_id="dup01", fen=_before_mate().fen())
    db_session.commit()

    game = _game(pgn=SCHOLAR)
    db_session.add(game)
    db_session.commit()
    assert analyze_pending(db_session, _engine(), SETTINGS) == 1

    proprio = db_session.scalars(select(Puzzle).where(Puzzle.source == "own")).one()
    assert proprio.fen_start == guardada.fen_start and proprio.kind == guardada.kind
    assert db_session.get(Puzzle, guardada.id) is not None


def test_erro_do_adversario_castigado_na_partida_nao_vira_exercicio(db_session):
    db_session.add(_game(pgn=SCHOLAR_COM_O_MATE, my_color="white"))
    db_session.commit()
    assert analyze_pending(db_session, _engine(), SETTINGS) == 1
    mistakes = db_session.scalars(select(Position).where(Position.is_mistake)).all()
    assert [(p.ply, p.mistake_by) for p in mistakes] == [(6, "opponent")]
    assert db_session.scalar(select(func.count(Puzzle.id))) == 0
