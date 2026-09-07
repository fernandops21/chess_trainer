from datetime import datetime, timedelta

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Puzzle, Review, Study, StudyChapter
from chess_trainer.core.srs.queue import QueueFilters, build_queue, count_new_reviewed_today, local_day_start
from tests.factories import make_puzzle

NOW = datetime(2026, 9, 4, 15, 0)
S = AppSettings(new_per_day=2)


def test_local_day_start_is_within_last_24h():
    start = local_day_start(NOW)
    assert start <= NOW and NOW - start < timedelta(hours=24)
    assert start.tzinfo is None
    from datetime import timezone
    start_local = start.replace(tzinfo=timezone.utc).astimezone()
    now_local = NOW.replace(tzinfo=timezone.utc).astimezone()
    assert (start_local.hour, start_local.minute, start_local.second) == (0, 0, 0)
    assert start_local.date() == now_local.date()


def test_due_puzzles_first_most_overdue_first(db_session):
    p_late = make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=3))
    p_soon = make_puzzle(db_session, fen="f2", due_at=NOW - timedelta(hours=1))
    make_puzzle(db_session, fen="f3", due_at=NOW + timedelta(days=1))  # ainda não venceu
    make_puzzle(db_session, fen="f4")                                   # novo
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert [p.id for p in q.due] == [p_late.id, p_soon.id]
    assert q.due_count == 2 and q.new == [] and q.new_available == 1


def test_new_only_when_nothing_due_recent_games_first_limited(db_session):
    old = make_puzzle(db_session, fen="f1", played_at=datetime(2026, 1, 1))
    mid = make_puzzle(db_session, fen="f2", played_at=datetime(2026, 5, 1))
    new = make_puzzle(db_session, fen="f3", played_at=datetime(2026, 8, 1))
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert q.due == [] and [p.id for p in q.new] == [new.id, mid.id]
    assert q.new_available == 3 and q.new_remaining_today == 2


def test_new_limit_discounts_new_reviewed_today(db_session):
    reviewed = make_puzzle(db_session, fen="f0", due_at=NOW + timedelta(days=1))
    db_session.add(Review(puzzle_id=reviewed.id, reviewed_at=NOW - timedelta(hours=2), result="correct",
                          ease=2.5, interval_days=1, due_at=NOW + timedelta(days=1), lapses=0))
    db_session.commit()
    make_puzzle(db_session, fen="f1"); make_puzzle(db_session, fen="f2")
    assert count_new_reviewed_today(db_session, NOW) == 1
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert len(q.new) == 1 and q.new_remaining_today == 1


def test_filters_and_leeches(db_session):
    make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=1), category="rapid", theme="fork", kind="punish", side="white")
    make_puzzle(db_session, fen="f2", due_at=NOW - timedelta(days=1), category="blitz", theme="fork", kind="avoid", side="black")
    make_puzzle(db_session, fen="f3", due_at=NOW - timedelta(days=1), is_leech=True)
    assert build_queue(db_session, QueueFilters(), S, NOW).due_count == 2
    assert build_queue(db_session, QueueFilters(category="blitz"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(theme="fork", kind="avoid"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(color="white"), S, NOW).due_count == 1
    assert build_queue(db_session, QueueFilters(theme="pin"), S, NOW).due_count == 0


# --- fontes de exercício (own / lichess / study) ---

S10 = AppSettings(new_per_day=10)


def _puzzle_externo(db, *, fen, source="lichess", chapter_id=None, created_at=datetime(2026, 5, 1),
                    due_at=None, external_id=None, in_queue=True) -> Puzzle:
    """Puzzle sem partida nem posição (Lichess ou estudo)."""
    puzzle = Puzzle(source=source, chapter_id=chapter_id, external_id=external_id, in_queue=in_queue,
                    kind="punish", fen_start=fen, side_to_move="white",
                    solution='{"moves": [{"uci": "a2a4", "by": "solver", "alternatives": []}]}',
                    end_reason="material_gain", theme="tactic", category="lichess", solver_moves=1,
                    created_at=created_at, srs_due_at=due_at)
    db.add(puzzle)
    db.commit()
    return puzzle


def _estudo_com_capitulo(db, *, titulo: str, ordem: int = 1) -> StudyChapter:
    estudo = Study(title=titulo, source_url=f"https://lichess.org/study/{titulo}")
    db.add(estudo)
    db.flush()
    capitulo = StudyChapter(study_id=estudo.id, order=ordem, name=f"{titulo} cap {ordem}",
                            fen="fen-cap", orientation="white", mode="gamebook", pgn="1. e4 *")
    db.add(capitulo)
    db.commit()
    return capitulo


def test_fora_da_fila_nao_e_servido_nem_contado(db_session):
    vencido = make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=1))
    vencido.in_queue = False
    novo = make_puzzle(db_session, fen="f2")
    novo.in_queue = False
    db_session.commit()
    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert q.due == [] and q.due_count == 0
    assert q.new == [] and q.new_available == 0


def test_filtro_por_fonte(db_session):
    proprio = make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=1))
    lichess = _puzzle_externo(db_session, fen="f2", due_at=NOW - timedelta(days=1))
    capitulo = _estudo_com_capitulo(db_session, titulo="estudo-a")
    estudo = _puzzle_externo(db_session, fen="f3", source="study", chapter_id=capitulo.id,
                             due_at=NOW - timedelta(days=1))

    todos = build_queue(db_session, QueueFilters(), S, NOW)
    assert {p.id for p in todos.due} == {proprio.id, lichess.id, estudo.id}

    so_lichess = build_queue(db_session, QueueFilters(sources=("lichess",)), S, NOW)
    assert [p.id for p in so_lichess.due] == [lichess.id] and so_lichess.due_count == 1

    dois = build_queue(db_session, QueueFilters(sources=("own", "study")), S, NOW)
    assert {p.id for p in dois.due} == {proprio.id, estudo.id}


def test_filtro_por_estudo(db_session):
    cap_a = _estudo_com_capitulo(db_session, titulo="estudo-a")
    cap_b = _estudo_com_capitulo(db_session, titulo="estudo-b")
    do_a = _puzzle_externo(db_session, fen="f1", source="study", chapter_id=cap_a.id,
                           due_at=NOW - timedelta(days=1))
    _puzzle_externo(db_session, fen="f2", source="study", chapter_id=cap_b.id, due_at=NOW - timedelta(days=1))
    make_puzzle(db_session, fen="f3", due_at=NOW - timedelta(days=1))

    q = build_queue(db_session, QueueFilters(study_id=cap_a.study_id), S, NOW)
    assert [p.id for p in q.due] == [do_a.id] and q.due_count == 1


def test_novos_de_fontes_diferentes_ordenados_por_data(db_session):
    antigo = make_puzzle(db_session, fen="f1", played_at=datetime(2026, 1, 1))
    do_meio = _puzzle_externo(db_session, fen="f2", created_at=datetime(2026, 5, 1))
    recente = make_puzzle(db_session, fen="f3", played_at=datetime(2026, 8, 1))
    q = build_queue(db_session, QueueFilters(), S10, NOW)
    assert [p.id for p in q.new] == [recente.id, do_meio.id, antigo.id]
    assert q.new_available == 3
