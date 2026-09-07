"""Testes do serviço de estudos: upsert, reimportação, fila e remoção."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from chess_trainer.core.models import Puzzle, Review, Study, StudyChapter, utcnow
from chess_trainer.core.studies.parser import parse_study_pgn
from chess_trainer.core.studies.service import (
    StudyNotFound,
    delete_study,
    fetch_study_pgn,
    parse_lichess_url,
    set_study_queue,
    upsert_study,
)
from tests.factories import make_puzzle

FIXTURE = Path(__file__).parent / "fixtures" / "study_4JKVAfaE.pgn"
AGORA = datetime(2026, 9, 6, 12, 0, 0)

ESTUDO = "Estudo de teste"
# posição de mate no corredor: a torre em a1 dá mate em um lance
FEN_MATE = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
# peão passado: dois lances do solucionador, sem mate
FEN_PEAO = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
# a mesma posição com o peão um lance à frente, para a reimportação com linha trocada
FEN_PEAO_AVANCADO = "4k3/8/8/8/8/4P3/8/4K3 w - - 0 1"


def capitulo_pgn(nome, url, fen, lances, modo="gamebook", estudo=ESTUDO, autor="autor"):
    """Monta o PGN de um capítulo no formato que o Lichess exporta."""
    linhas = [
        f'[Event "{estudo}: {nome}"]',
        '[Result "*"]',
        f'[StudyName "{estudo}"]',
        f'[ChapterName "{nome}"]',
    ]
    if url:
        linhas.append(f'[ChapterURL "{url}"]')
    if modo == "gamebook":
        linhas.append('[ChapterMode "gamebook"]')
    linhas += [
        f'[Annotator "https://lichess.org/@/{autor}"]',
        '[SetUp "1"]',
        f'[FEN "{fen}"]',
        "",
        f"{lances} *",
        "",
    ]
    return "\n".join(linhas)


def estudo_pgn(*capitulos: str) -> str:
    return "\n".join(capitulos)


@pytest.fixture(scope="module")
def texto_da_fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def importar(db, texto, source_url="", now=AGORA):
    return upsert_study(db, parse_study_pgn(texto), source_url, now)


# --- upsert com a fixture real -------------------------------------------


def test_upsert_da_fixture_cria_capitulos_e_exercicios(db_session, texto_da_fixture):
    study, report = importar(db_session, texto_da_fixture, "https://lichess.org/study/4JKVAfaE")

    assert study.lichess_id == "4JKVAfaE" and study.author == "basso01"
    assert study.title.startswith("#PL05A") and study.imported_at == AGORA
    assert len(study.chapters) == 27
    assert [c.order for c in study.chapters] == list(range(1, 28))
    puzzles = db_session.scalars(select(Puzzle).where(Puzzle.source == "study")).all()
    assert len(puzzles) == 15
    assert report.created == 15 and report.updated == 0 and report.skipped == []
    p = next(p for p in puzzles if p.chapter_id == study.chapters[0].id)
    assert p.kind == "punish" and p.category == "study" and p.theme == "study"
    assert p.in_queue is True and p.fen_start == study.chapters[0].fen
    assert p.side_to_move in {"white", "black"} and p.solver_moves >= 1
    assert p.end_reason in {"mate", "material_gain"}
    assert study.chapters[0].puzzle_id == p.id
    # capítulos de leitura ficam sem exercício
    leitura = [c for c in study.chapters if c.mode == "read"]
    assert len(leitura) == 12 and all(c.puzzle_id is None for c in leitura)


def test_reimportar_o_mesmo_pgn_nao_duplica(db_session, texto_da_fixture):
    study, _ = importar(db_session, texto_da_fixture)
    antes = {c.lichess_url: c.puzzle_id for c in study.chapters}

    study2, report = importar(db_session, texto_da_fixture, now=AGORA + timedelta(days=1))

    assert study2.id == study.id
    assert db_session.scalar(select(func.count(Study.id))) == 1
    assert db_session.scalar(select(func.count(StudyChapter.id))) == 27
    assert db_session.scalar(select(func.count(Puzzle.id))) == 15
    assert report.created == 0 and report.updated == 15
    assert {c.lichess_url: c.puzzle_id for c in study2.chapters} == antes


# --- reimportação com mudanças -------------------------------------------


def _dois_capitulos(lances_primeiro="1. e4 Kd7 2. e5", fen_primeiro=FEN_PEAO):
    return estudo_pgn(
        capitulo_pgn("Um", "https://lichess.org/study/TESTE001/cap00001", fen_primeiro, lances_primeiro),
        capitulo_pgn("Dois", "https://lichess.org/study/TESTE001/cap00002", FEN_MATE, "1. Ra8#"),
    )


def test_capitulo_ausente_sai_da_fila_sem_ser_apagado(db_session):
    study, _ = importar(db_session, _dois_capitulos())
    segundo = study.chapters[1]
    puzzle_id = segundo.puzzle_id

    so_o_primeiro = capitulo_pgn("Um", "https://lichess.org/study/TESTE001/cap00001", FEN_PEAO, "1. e4 Kd7 2. e5")
    importar(db_session, so_o_primeiro)

    db_session.expire_all()
    segundo = db_session.get(StudyChapter, segundo.id)
    assert segundo is not None and segundo.in_queue is False
    assert db_session.get(Puzzle, puzzle_id).in_queue is False
    # o capítulo que continua no estudo não é afetado
    assert db_session.get(StudyChapter, study.chapters[0].id).in_queue is True


def test_linha_alterada_atualiza_o_exercicio_no_lugar(db_session):
    study, _ = importar(db_session, _dois_capitulos())
    puzzle = db_session.get(Puzzle, study.chapters[0].puzzle_id)
    puzzle.srs_ease, puzzle.srs_interval_days, puzzle.srs_due_at = 2.9, 12, AGORA
    db_session.commit()

    _, report = importar(db_session, _dois_capitulos("1. e4 Kd7 2. e5 Kc6", FEN_PEAO_AVANCADO))

    db_session.expire_all()
    atualizado = db_session.get(Puzzle, puzzle.id)
    assert atualizado.id == puzzle.id and report.updated == 2 and report.created == 0
    ucis = [m["uci"] for m in json.loads(atualizado.solution)["moves"]]
    assert ucis[0] == "e3e4" and len(ucis) == 4
    assert atualizado.solver_moves == 2
    # a fen inicial acompanha a nova versão do capítulo
    assert atualizado.fen_start == db_session.get(StudyChapter, study.chapters[0].id).fen
    # o histórico da repetição espaçada continua intocado
    assert atualizado.srs_ease == 2.9 and atualizado.srs_interval_days == 12 and atualizado.srs_due_at == AGORA


def test_capitulo_com_lance_ilegal_entra_no_relatorio_sem_exercicio(db_session):
    texto = capitulo_pgn("Torto", "https://lichess.org/study/TESTE001/cap00003", FEN_PEAO, "1. e4 Ke7 2. Qh5")
    study, report = importar(db_session, texto)

    assert len(report.skipped) == 1 and "Torto" in report.skipped[0]
    assert report.created == 0
    assert study.chapters[0].puzzle_id is None
    assert db_session.scalar(select(func.count(Puzzle.id))) == 0


# --- desfecho e lado a mover ---------------------------------------------


def test_desfecho_mate_ou_ganho_de_material(db_session):
    study, _ = importar(db_session, _dois_capitulos())
    peao = db_session.get(Puzzle, study.chapters[0].puzzle_id)
    mate = db_session.get(Puzzle, study.chapters[1].puzzle_id)

    assert peao.end_reason == "material_gain" and peao.solver_moves == 2 and peao.side_to_move == "white"
    assert mate.end_reason == "mate" and mate.solver_moves == 1 and mate.side_to_move == "white"


def test_fen_repetida_em_outro_estudo_nao_mexe_no_exercicio_alheio(db_session):
    primeiro = capitulo_pgn("Um", "https://lichess.org/study/AAAAAAAA/cap00001", FEN_MATE, "1. Ra8#", estudo="A")
    segundo = capitulo_pgn("Outro", "https://lichess.org/study/BBBBBBBB/cap00002", FEN_MATE,
                           "1. Ra7 Kf8 2. Rb7", estudo="B")
    estudo_a, _ = importar(db_session, primeiro)
    capitulo_a, puzzle_id = estudo_a.chapters[0].id, estudo_a.chapters[0].puzzle_id
    db_session.add(Review(puzzle_id=puzzle_id, reviewed_at=utcnow(), result="ok",
                          ease=2.5, interval_days=1, due_at=utcnow(), lapses=0))
    db_session.commit()

    estudo_b, report = importar(db_session, segundo)

    assert estudo_b.id != estudo_a.id
    db_session.expire_all()
    # a única (fen_start, kind, source) não deixa dois exercícios de estudo com a
    # mesma posição inicial: o exercício continua sendo do capítulo do estudo A
    exercicio = db_session.get(Puzzle, puzzle_id)
    assert exercicio.chapter_id == capitulo_a
    assert [m["uci"] for m in json.loads(exercicio.solution)["moves"]] == ["a1a8"]
    assert db_session.scalar(select(func.count(Review.id))) == 1
    # o capítulo do estudo B fica sem exercício e a colisão vai para o relatório
    assert db_session.get(Study, estudo_b.id).chapters[0].puzzle_id is None
    assert report.created == 0 and report.updated == 0
    assert report.skipped == ["1. Outro: posição inicial já usada por outro capítulo"]
    assert db_session.scalar(select(func.count(Puzzle.id))) == 1

    delete_study(db_session, db_session.get(Study, estudo_b.id))

    db_session.expire_all()
    assert db_session.get(Puzzle, puzzle_id) is not None
    assert db_session.get(StudyChapter, capitulo_a).puzzle_id == puzzle_id
    assert db_session.scalar(select(func.count(Review.id))) == 1


def test_fen_repetida_no_mesmo_estudo_pula_o_segundo_capitulo(db_session):
    texto = estudo_pgn(
        capitulo_pgn("Um", "https://lichess.org/study/TESTE001/cap00001", FEN_MATE, "1. Ra8#"),
        capitulo_pgn("Dois", "https://lichess.org/study/TESTE001/cap00002", FEN_MATE, "1. Ra7 Kf8 2. Rb7"),
    )

    study, report = importar(db_session, texto)

    assert study.chapters[0].puzzle_id is not None
    assert study.chapters[1].puzzle_id is None
    assert report.created == 1 and report.updated == 0
    assert report.skipped == ["2. Dois: posição inicial já usada por outro capítulo"]
    assert db_session.scalar(select(func.count(Puzzle.id)).where(Puzzle.in_queue.is_(True))) == 1


# --- fila e remoção ------------------------------------------------------


def test_set_study_queue_tira_e_devolve_capitulos_e_exercicios(db_session):
    study, _ = importar(db_session, _dois_capitulos())

    set_study_queue(db_session, study, False)
    db_session.expire_all()
    puzzles = db_session.scalars(select(Puzzle).where(Puzzle.source == "study")).all()
    assert all(p.in_queue is False for p in puzzles)
    assert all(c.in_queue is False for c in db_session.get(Study, study.id).chapters)

    set_study_queue(db_session, db_session.get(Study, study.id), True)
    db_session.expire_all()
    puzzles = db_session.scalars(select(Puzzle).where(Puzzle.source == "study")).all()
    assert all(p.in_queue is True for p in puzzles)


def test_delete_study_apaga_so_o_que_o_estudo_criou(db_session):
    proprio = make_puzzle(db_session, fen="r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    study, _ = importar(db_session, _dois_capitulos())
    puzzle_ids = [c.puzzle_id for c in study.chapters]
    db_session.add(Review(puzzle_id=puzzle_ids[0], reviewed_at=utcnow(), result="ok",
                          ease=2.5, interval_days=1, due_at=utcnow(), lapses=0))
    db_session.add(Review(puzzle_id=proprio.id, reviewed_at=utcnow(), result="ok",
                          ease=2.5, interval_days=1, due_at=utcnow(), lapses=0))
    db_session.commit()

    delete_study(db_session, study)

    assert db_session.scalar(select(func.count(Study.id))) == 0
    assert db_session.scalar(select(func.count(StudyChapter.id))) == 0
    assert db_session.scalar(select(func.count(Puzzle.id))) == 1
    assert db_session.get(Puzzle, proprio.id) is not None
    assert db_session.scalar(select(func.count(Review.id))) == 1


# --- URL e download ------------------------------------------------------


@pytest.mark.parametrize(
    "url, esperado",
    [
        ("https://lichess.org/study/4JKVAfaE", "4JKVAfaE"),
        ("https://lichess.org/study/4JKVAfaE/Pt2y3ild", "4JKVAfaE"),
        ("lichess.org/study/4JKVAfaE/", "4JKVAfaE"),
        ("/study/4JKVAfaE", "4JKVAfaE"),
        ("study/4JKVAfaE", "4JKVAfaE"),
        ("https://lichess.org/study/4JKVAfaE?page=2", "4JKVAfaE"),
        ("lixo", None),
        ("", None),
        ("https://lichess.org/4JKVAfaE", None),
    ],
)
def test_parse_lichess_url(url, esperado):
    assert parse_lichess_url(url) == esperado


def _http(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_study_pgn_devolve_o_texto():
    def handler(request):
        assert request.url.path == "/api/study/4JKVAfaE.pgn"
        return httpx.Response(200, text="[Event \"x\"]\n\n*\n")

    assert fetch_study_pgn("4JKVAfaE", _http(handler)).startswith("[Event")


def test_fetch_study_pgn_404_vira_study_not_found():
    with pytest.raises(StudyNotFound):
        fetch_study_pgn("4JKVAfaE", _http(lambda request: httpx.Response(404, text="")))


def test_fetch_study_pgn_erro_http_vira_runtime_error():
    with pytest.raises(RuntimeError, match="500"):
        fetch_study_pgn("4JKVAfaE", _http(lambda request: httpx.Response(500, text="")))


# --- árvore de lances do capítulo ----------------------------------------


def test_importacao_grava_a_arvore_e_a_origem(db_session, texto_da_fixture):
    study, _ = importar(db_session, texto_da_fixture)
    assert study.origin == "lichess"
    capitulo = study.chapters[0]
    tree = json.loads(capitulo.tree_json)
    assert tree["fen"] == capitulo.fen and tree["orientation"] == capitulo.orientation
    assert [n["san"] for n in tree["root"]["children"]] == ["Qb6+", "O-O", "Bg6"]
    # capítulos de leitura também guardam a árvore
    leitura = next(c for c in study.chapters if c.mode == "read")
    assert json.loads(leitura.tree_json)["root"]["children"] is not None


def test_ensure_tree_preenche_capitulo_sem_arvore(db_session):
    from chess_trainer.core.studies.service import ensure_tree

    texto = capitulo_pgn("Um", "https://lichess.org/study/ABCD1234/EFGH5678", FEN_MATE, "1. Ra8#")
    study, _ = importar(db_session, texto)
    capitulo = study.chapters[0]
    capitulo.tree_json = ""  # como ficam os capítulos importados antes do editor
    db_session.commit()

    tree = ensure_tree(capitulo)
    db_session.commit()
    assert [n["san"] for n in tree["root"]["children"]] == ["Ra8#"]
    assert json.loads(capitulo.tree_json) == tree
