import random
from datetime import datetime, timedelta

from chess_trainer.config import AppSettings
from chess_trainer.core.models import Puzzle, Review, Study, StudyChapter
from chess_trainer.core.srs.queue import QueueFilters, build_queue, count_new_reviewed_today, local_day_start
from tests.factories import make_puzzle

NOW = datetime(2026, 9, 4, 15, 0)
S = AppSettings(new_per_day=2)
S_RECENTES = AppSettings(new_per_day=2, new_order="recent")


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


def test_modo_novos_com_ordem_recente_traz_as_partidas_mais_novas_primeiro(db_session):
    make_puzzle(db_session, fen="f1", played_at=datetime(2026, 1, 1))
    meio = make_puzzle(db_session, fen="f2", played_at=datetime(2026, 5, 1))
    recente = make_puzzle(db_session, fen="f3", played_at=datetime(2026, 8, 1))
    q = build_queue(db_session, QueueFilters(mode="new"), S_RECENTES, NOW)
    assert q.due == [] and [p.id for p in q.new] == [recente.id, meio.id]
    assert [p.id for p in q.items] == [recente.id, meio.id]
    assert q.new_available == 3 and q.new_remaining_today == 2


def test_new_limit_discounts_new_reviewed_today(db_session):
    reviewed = make_puzzle(db_session, fen="f0", due_at=NOW + timedelta(days=1))
    db_session.add(Review(puzzle_id=reviewed.id, reviewed_at=NOW - timedelta(hours=2), result="correct",
                          ease=2.5, interval_days=1, due_at=NOW + timedelta(days=1), lapses=0))
    db_session.commit()
    make_puzzle(db_session, fen="f1"); make_puzzle(db_session, fen="f2")
    assert count_new_reviewed_today(db_session, NOW) == 1
    q = build_queue(db_session, QueueFilters(mode="new"), S, NOW)
    assert len(q.new) == 1 and q.new_remaining_today == 1


def test_new_remaining_today_conta_so_revisoes_de_puzzles_proprios(db_session):
    """O limite diário de "novos" é só sobre os erros do próprio usuário: revisar
    pela primeira vez exercícios de estudo hoje não pode descontar dele."""
    from chess_trainer.core.models import Study, StudyChapter

    estudo = Study(title="estudo-a", source_url="https://lichess.org/study/estudo-a")
    db_session.add(estudo)
    db_session.flush()
    capitulo = StudyChapter(study_id=estudo.id, order=1, name="estudo-a cap 1", fen="fen-cap",
                            orientation="white", mode="gamebook", pgn="1. e4 *")
    db_session.add(capitulo)
    db_session.commit()
    for i in range(10):
        p = Puzzle(source="study", chapter_id=capitulo.id, kind="punish", fen_start=f"e{i}",
                   side_to_move="white",
                   solution='{"moves": [{"uci": "a2a4", "by": "solver", "alternatives": []}]}',
                   end_reason="material_gain", theme="tactic", category="lichess", solver_moves=1)
        db_session.add(p)
        db_session.flush()
        db_session.add(Review(puzzle_id=p.id, reviewed_at=NOW - timedelta(hours=1), result="correct",
                              ease=2.5, interval_days=1, due_at=NOW + timedelta(days=1), lapses=0))
    db_session.commit()
    assert count_new_reviewed_today(db_session, NOW) == 0
    q = build_queue(db_session, QueueFilters(mode="new"), S, NOW)
    assert q.new_remaining_today == S.new_per_day

    proprio = make_puzzle(db_session, fen="p1")
    db_session.add(Review(puzzle_id=proprio.id, reviewed_at=NOW - timedelta(hours=1), result="correct",
                          ease=2.5, interval_days=1, due_at=NOW + timedelta(days=1), lapses=0))
    db_session.commit()
    assert count_new_reviewed_today(db_session, NOW) == 1
    q2 = build_queue(db_session, QueueFilters(mode="new"), S, NOW)
    assert q2.new_remaining_today == S.new_per_day - 1


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


def test_novos_sao_so_os_dos_meus_erros(db_session):
    """"Novos" serve a primeira vez dos erros do usuário; táticas e estudos
    entram na repetição pela tela deles, não por aqui."""
    antigo = make_puzzle(db_session, fen="f1", played_at=datetime(2026, 1, 1))
    recente = make_puzzle(db_session, fen="f3", played_at=datetime(2026, 8, 1))
    _puzzle_externo(db_session, fen="f2", created_at=datetime(2026, 5, 1))
    capitulo = _estudo_com_capitulo(db_session, titulo="estudo-a")
    _puzzle_externo(db_session, fen="f4", source="study", chapter_id=capitulo.id)

    q = build_queue(db_session, QueueFilters(mode="new"), AppSettings(new_per_day=10, new_order="recent"), NOW)
    assert [p.id for p in q.new] == [recente.id, antigo.id]
    assert q.new_available == 2


# --- modos de treino (repetição / novos / estudo) ---


def _estudo_com_capitulos(db, *, titulo: str, quantos: int) -> list[StudyChapter]:
    estudo = Study(title=titulo, source_url=f"https://lichess.org/study/{titulo}")
    db.add(estudo)
    db.flush()
    capitulos = [StudyChapter(study_id=estudo.id, order=i, name=f"{titulo} cap {i}",
                              fen=f"fen-cap-{i}", orientation="white", mode="gamebook", pgn="1. e4 *")
                 for i in range(1, quantos + 1)]
    db.add_all(capitulos)
    db.commit()
    return capitulos


def test_modo_repeticao_so_serve_exercicios_ja_revisados(db_session):
    vencido = make_puzzle(db_session, fen="f1", due_at=NOW - timedelta(days=1))
    make_puzzle(db_session, fen="f2")                                  # nunca revisado
    make_puzzle(db_session, fen="f3", due_at=NOW + timedelta(days=1))  # revisado, mas não venceu

    q = build_queue(db_session, QueueFilters(), S, NOW)
    assert [p.id for p in q.items] == [vencido.id]
    assert q.due_count == 1 and q.new == [] and q.new_available == 1


def _venc(minutos: int) -> datetime:
    """Instante dentro do dia local de NOW (para agrupar vencidos por dia)."""
    return local_day_start(NOW) + timedelta(minutes=minutos)


def test_modo_repeticao_agrupa_por_dia_e_embaralha_dentro_do_dia(db_session):
    ontem = make_puzzle(db_session, fen="f0", due_at=_venc(-60))
    hoje = [make_puzzle(db_session, fen=f"f{i}", due_at=_venc(i)) for i in range(1, 6)]
    na_ordem = [p.id for p in hoje]

    q = build_queue(db_session, QueueFilters(), S, NOW, rng=random.Random(3))
    assert q.items[0].id == ontem.id, "o dia mais atrasado vem primeiro"
    servidos = [p.id for p in q.items[1:]]
    assert sorted(servidos) == sorted(na_ordem), "o dia de hoje vem inteiro, sem repetir nem perder"
    assert servidos != na_ordem, "dentro do dia a ordem é sorteada"

    de_novo = build_queue(db_session, QueueFilters(), S, NOW, rng=random.Random(3))
    assert [p.id for p in de_novo.items] == [p.id for p in q.items], "mesma semente, mesma ordem"


def test_modo_novos_aleatorio_ignora_a_data_da_partida(db_session):
    ids = [make_puzzle(db_session, fen=f"f{i}", played_at=datetime(2026, i, 1)).id for i in range(1, 7)]
    por_data = list(reversed(ids))

    q = build_queue(db_session, QueueFilters(mode="new"), AppSettings(new_per_day=6), NOW,
                    rng=random.Random(3))
    servidos = [p.id for p in q.items]
    assert sorted(servidos) == sorted(ids) and servidos != por_data
    assert q.new_available == 6 and q.new_remaining_today == 6


def test_modo_novos_respeita_o_limite_diario_no_sorteio(db_session):
    for i in range(1, 6):
        make_puzzle(db_session, fen=f"f{i}")
    q = build_queue(db_session, QueueFilters(mode="new"), S, NOW, rng=random.Random(1))
    assert len(q.items) == 2 and len(set(p.id for p in q.items)) == 2
    assert q.new_available == 5 and q.new_remaining_today == 2


def test_modo_estudo_traz_tudo_na_ordem_dos_capitulos_sem_limite(db_session):
    caps = _estudo_com_capitulos(db_session, titulo="estudo-a", quantos=3)
    terceiro = _puzzle_externo(db_session, fen="f3", source="study", chapter_id=caps[2].id)
    primeiro = _puzzle_externo(db_session, fen="f1", source="study", chapter_id=caps[0].id,
                               due_at=NOW - timedelta(days=1))
    segundo = _puzzle_externo(db_session, fen="f2", source="study", chapter_id=caps[1].id,
                              due_at=NOW + timedelta(days=5))
    outro = _estudo_com_capitulo(db_session, titulo="estudo-b")
    _puzzle_externo(db_session, fen="f9", source="study", chapter_id=outro.id)

    q = build_queue(db_session, QueueFilters(mode="study", study_id=caps[0].study_id),
                    AppSettings(new_per_day=1), NOW)
    assert [p.id for p in q.items] == [primeiro.id, segundo.id, terceiro.id]
    assert q.due_count == 1 and q.new_available == 1


def test_modo_estudo_ignora_fora_da_fila_e_sanguessuga(db_session):
    caps = _estudo_com_capitulos(db_session, titulo="estudo-a", quantos=3)
    fica = _puzzle_externo(db_session, fen="f1", source="study", chapter_id=caps[0].id)
    _puzzle_externo(db_session, fen="f2", source="study", chapter_id=caps[1].id, in_queue=False)
    sanguessuga = _puzzle_externo(db_session, fen="f3", source="study", chapter_id=caps[2].id)
    sanguessuga.is_leech = True
    db_session.commit()

    q = build_queue(db_session, QueueFilters(mode="study", study_id=caps[0].study_id), S, NOW)
    assert [p.id for p in q.items] == [fica.id]
