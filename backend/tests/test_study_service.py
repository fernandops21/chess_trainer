"""Testes do serviço de estudos: upsert, reimportação, edição, fila e remoção."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from chess_trainer.core.models import Puzzle, Review, Study, StudyChapter, utcnow
from chess_trainer.core.studies.parser import parse_study_pgn
from chess_trainer.core.studies.service import (
    ChapterOrderError,
    StudyNotFound,
    TreeInvalid,
    chapter_detail,
    create_chapter,
    create_study,
    delete_chapter,
    delete_study,
    duplicate_chapter,
    fetch_study_pgn,
    parse_lichess_url,
    save_chapter,
    set_study_queue,
    update_study,
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
    assert len(puzzles) == 16
    assert report.created == 16 and report.updated == 0 and report.skipped == []
    p = next(p for p in puzzles if p.chapter_id == study.chapters[0].id)
    assert p.kind == "punish" and p.category == "study" and p.theme == "study"
    assert p.in_queue is True and p.fen_start == study.chapters[0].fen
    assert p.side_to_move in {"white", "black"} and p.solver_moves >= 1
    assert p.end_reason in {"mate", "material_gain"}
    assert study.chapters[0].puzzle_id == p.id
    # capítulos de leitura ficam sem exercício
    leitura = [c for c in study.chapters if c.mode == "read"]
    assert len(leitura) == 11 and all(c.puzzle_id is None for c in leitura)


def test_reimportar_o_mesmo_pgn_nao_duplica(db_session, texto_da_fixture):
    study, _ = importar(db_session, texto_da_fixture)
    antes = {c.lichess_url: c.puzzle_id for c in study.chapters}

    study2, report = importar(db_session, texto_da_fixture, now=AGORA + timedelta(days=1))

    assert study2.id == study.id
    assert db_session.scalar(select(func.count(Study.id))) == 1
    assert db_session.scalar(select(func.count(StudyChapter.id))) == 27
    assert db_session.scalar(select(func.count(Puzzle.id))) == 16
    assert report.created == 0 and report.updated == 16
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


# --- edição local: estudo e capítulos ------------------------------------


def arvore_mate():
    """Mate em um com enunciado, seta na raiz e uma variação comentada."""
    return {
        "fen": FEN_MATE,
        "orientation": "white",
        "intro": "Mate em um.",
        "root": {
            "shapes": [{"orig": "a1", "dest": "a8", "brush": "green"}],
            "children": [
                {"id": "n1", "uci": "a1a8", "san": "Ra8#", "comment": "Mate!",
                 "shapes": [], "nags": [], "children": []},
                {"id": "n2", "uci": "a1a7", "san": "Ra7", "comment": "Deixa o rei escapar.",
                 "shapes": [], "nags": [2], "children": []},
            ],
        },
    }


def arvore_linear(fen, lances, intro=""):
    """Árvore só com a linha principal; `lances` são pares (uci, san)."""
    raiz = {"shapes": [], "children": []}
    atual = raiz
    for i, (uci, san) in enumerate(lances, start=1):
        node = {"id": f"n{i}", "uci": uci, "san": san, "comment": "",
                "shapes": [], "nags": [], "children": []}
        atual["children"].append(node)
        atual = node
    return {"fen": fen, "orientation": "white", "intro": intro, "root": raiz}


LANCES_PEAO = [("e2e4", "e4"), ("e8d7", "Kd7"), ("e4e5", "e5")]


def estudo_local(db, titulo=ESTUDO, autor="eu"):
    return create_study(db, titulo, autor)


def test_criar_estudo_local_fica_com_origin_local(db_session):
    study = create_study(db_session, "  Meu estudo  ", "eu")

    assert study.origin == "local" and study.title == "Meu estudo" and study.author == "eu"
    assert study.lichess_id is None and study.source_url == "" and study.imported_at is None
    assert study.updated_at is not None and study.chapters == []


def test_criar_capitulo_comeca_com_arvore_vazia(db_session):
    study = estudo_local(db_session)

    chapter = create_chapter(db_session, study, "Um", FEN_MATE, "black", "gamebook")

    assert chapter.order == 1 and chapter.name == "Um" and chapter.orientation == "black"
    assert chapter.fen == FEN_MATE and chapter.mode == "gamebook"
    arvore = json.loads(chapter.tree_json)
    assert arvore["root"]["children"] == [] and arvore["orientation"] == "black"
    # sem lances não há exercício, mesmo em gamebook
    assert chapter.puzzle_id is None
    assert "[FEN " in chapter.pgn and "[Orientation " in chapter.pgn


def test_criar_capitulo_com_fen_invalida_recusa(db_session):
    study = estudo_local(db_session)

    with pytest.raises(TreeInvalid) as exc:
        create_chapter(db_session, study, "Torto", "posição inventada")

    assert exc.value.errors and "FEN inválida" in exc.value.errors[0]


def test_salvar_capitulo_cria_o_exercicio_com_variacao_e_seta(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)

    save_chapter(db_session, chapter, "Mate no corredor", "gamebook", "white", arvore_mate())

    puzzle = db_session.get(Puzzle, chapter.puzzle_id)
    assert puzzle is not None and puzzle.source == "study" and puzzle.in_queue is True
    assert puzzle.fen_start == FEN_MATE and puzzle.side_to_move == "white"
    assert puzzle.solver_moves == 1 and puzzle.end_reason == "mate"
    solucao = json.loads(puzzle.solution)
    assert [m["uci"] for m in solucao["moves"]] == ["a1a8"]
    assert solucao["wrong_moves"] == {"a1a7": "Deixa o rei escapar."}
    assert solucao["comments"] == {"0": "Mate!"}
    assert solucao["shapes"] == {"start": [{"orig": "a1", "dest": "a8", "brush": "green"}]}
    assert solucao["intro"] == "Mate em um."
    # o capítulo guarda a árvore, o enunciado e o PGN gerado a partir dela
    assert chapter.name == "Mate no corredor" and chapter.intro_comment == "Mate em um."
    assert json.loads(chapter.tree_json)["root"]["children"][1]["uci"] == "a1a7"
    assert "[%cal Ga1a8]" in chapter.pgn and "Ra8#" in chapter.pgn
    assert chapter.updated_at is not None


def test_salvar_de_novo_com_a_mesma_linha_mantem_id_e_historico(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)
    save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore_mate())
    puzzle_id = chapter.puzzle_id
    puzzle = db_session.get(Puzzle, puzzle_id)
    puzzle.srs_ease, puzzle.srs_interval_days, puzzle.srs_due_at = 2.9, 12, AGORA
    db_session.add(Review(puzzle_id=puzzle_id, reviewed_at=AGORA, result="ok",
                          ease=2.9, interval_days=12, due_at=AGORA, lapses=0))
    db_session.commit()

    arvore = arvore_mate()
    arvore["root"]["children"][0]["comment"] = "Mate no corredor!"
    save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore)

    db_session.expire_all()
    atualizado = db_session.get(Puzzle, puzzle_id)
    assert db_session.get(StudyChapter, chapter.id).puzzle_id == puzzle_id
    assert atualizado.srs_ease == 2.9 and atualizado.srs_interval_days == 12
    assert atualizado.srs_due_at == AGORA
    assert json.loads(atualizado.solution)["comments"] == {"0": "Mate no corredor!"}
    assert db_session.scalar(select(func.count(Review.id))) == 1


def test_mudar_a_linha_principal_troca_a_solucao_no_lugar(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_PEAO)
    save_chapter(db_session, chapter, "Um", "gamebook", "white",
                 arvore_linear(FEN_PEAO, LANCES_PEAO[:1]))
    puzzle_id = chapter.puzzle_id

    save_chapter(db_session, chapter, "Um", "gamebook", "white",
                 arvore_linear(FEN_PEAO, LANCES_PEAO))

    db_session.expire_all()
    atualizado = db_session.get(Puzzle, puzzle_id)
    assert db_session.get(StudyChapter, chapter.id).puzzle_id == puzzle_id
    assert [m["uci"] for m in json.loads(atualizado.solution)["moves"]] == ["e2e4", "e8d7", "e4e5"]
    assert atualizado.solver_moves == 2


def test_virar_leitura_tira_o_exercicio_da_fila_e_voltar_devolve(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)
    save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore_mate())
    puzzle_id = chapter.puzzle_id

    save_chapter(db_session, chapter, "Um", "read", "white", arvore_mate())

    db_session.expire_all()
    assert db_session.get(Puzzle, puzzle_id).in_queue is False
    # nada foi apagado: o capítulo continua apontando para o exercício
    assert db_session.get(StudyChapter, chapter.id).puzzle_id == puzzle_id

    save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore_mate())

    db_session.expire_all()
    assert db_session.get(Puzzle, puzzle_id).in_queue is True


def test_exercicio_tirado_da_fila_na_mao_continua_fora_ao_salvar_o_capitulo(db_session):
    """Salvar um capítulo que já era gamebook não desfaz a saída da fila feita na
    tela de treino (`POST /puzzles/{id}/queue`); só voltar de leitura devolve."""
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)
    save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore_mate())
    puzzle_id = chapter.puzzle_id
    db_session.get(Puzzle, puzzle_id).in_queue = False
    db_session.commit()

    arvore = arvore_mate()
    arvore["root"]["children"][0]["comment"] = "Mate no corredor!"
    save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore)

    db_session.expire_all()
    assert db_session.get(Puzzle, puzzle_id).in_queue is False


def test_mudar_a_posicao_inicial_para_a_de_outro_capitulo_recusa(db_session):
    study = estudo_local(db_session)
    um = create_chapter(db_session, study, "Um", FEN_MATE)
    save_chapter(db_session, um, "Um", "gamebook", "white", arvore_mate())
    dois = create_chapter(db_session, study, "Dois", FEN_PEAO)
    save_chapter(db_session, dois, "Dois", "gamebook", "white", arvore_linear(FEN_PEAO, LANCES_PEAO))
    dois_id, puzzle_de_dois = dois.id, dois.puzzle_id

    with pytest.raises(TreeInvalid) as exc:
        save_chapter(db_session, dois, "Dois", "gamebook", "white", arvore_mate())

    assert exc.value.errors == ["posição inicial já usada por outro capítulo"]
    db_session.rollback()
    db_session.expire_all()
    # nada foi gravado: o exercício do capítulo continua o mesmo, na posição dele
    assert db_session.get(StudyChapter, dois_id).puzzle_id == puzzle_de_dois
    assert db_session.get(Puzzle, puzzle_de_dois).fen_start == FEN_PEAO


def test_salvar_com_fen_que_nao_e_texto_recusa(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)
    arvore = arvore_mate()
    arvore["fen"] = 5

    with pytest.raises(TreeInvalid) as exc:
        save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore)

    assert any("FEN inválida" in erro for erro in exc.value.errors)


def test_salvar_com_enunciado_que_nao_e_texto_recusa(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)
    arvore = arvore_mate()
    arvore["intro"] = 5

    with pytest.raises(TreeInvalid) as exc:
        save_chapter(db_session, chapter, "Um", "gamebook", "white", arvore)

    assert any("enunciado" in erro for erro in exc.value.errors)


def test_modo_e_orientacao_invalidos_recusam(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)

    with pytest.raises(TreeInvalid) as modo:
        save_chapter(db_session, chapter, "Um", "livro", "white", arvore_mate())
    with pytest.raises(TreeInvalid) as orientacao:
        save_chapter(db_session, chapter, "Um", "gamebook", "cima", arvore_mate())

    assert modo.value.errors == ["modo inválido"]
    assert orientacao.value.errors == ["orientação inválida"]
    db_session.expire_all()
    assert db_session.get(StudyChapter, chapter.id).mode == "read"


def test_salvar_arvore_com_lance_ilegal_recusa_sem_gravar(db_session):
    study = estudo_local(db_session)
    chapter = create_chapter(db_session, study, "Um", FEN_MATE)
    torta = arvore_linear(FEN_MATE, [("a1a8", "Ra8#"), ("g8h8", "Kh8")])

    with pytest.raises(TreeInvalid) as exc:
        save_chapter(db_session, chapter, "Um", "gamebook", "white", torta)

    assert any("lance ilegal" in erro for erro in exc.value.errors)
    assert db_session.get(StudyChapter, chapter.id).puzzle_id is None


def test_apagar_capitulo_apaga_exercicio_revisoes_e_renumera(db_session):
    study = estudo_local(db_session)
    um = create_chapter(db_session, study, "Um", FEN_MATE)
    save_chapter(db_session, um, "Um", "gamebook", "white", arvore_mate())
    dois = create_chapter(db_session, study, "Dois", FEN_PEAO)
    save_chapter(db_session, dois, "Dois", "gamebook", "white", arvore_linear(FEN_PEAO, LANCES_PEAO))
    tres = create_chapter(db_session, study, "Três", FEN_PEAO_AVANCADO, mode="read")
    for capitulo in (um, dois):
        db_session.add(Review(puzzle_id=capitulo.puzzle_id, reviewed_at=AGORA, result="ok",
                              ease=2.5, interval_days=1, due_at=AGORA, lapses=0))
    db_session.commit()
    apagado, exercicio_apagado = dois.id, dois.puzzle_id
    um_id, tres_id, puzzle_de_um = um.id, tres.id, um.puzzle_id

    delete_chapter(db_session, dois)

    db_session.expire_all()
    assert db_session.get(StudyChapter, apagado) is None
    assert db_session.get(Puzzle, exercicio_apagado) is None
    assert db_session.scalar(select(func.count(Review.id))) == 1
    # o exercício do outro capítulo continua inteiro e a ordem fecha sem buracos
    assert db_session.get(Puzzle, puzzle_de_um) is not None
    restantes = db_session.get(Study, study.id).chapters
    assert [(c.id, c.order) for c in restantes] == [(um_id, 1), (tres_id, 2)]


def test_duplicar_capitulo_copia_a_arvore_como_leitura(db_session):
    study = estudo_local(db_session)
    um = create_chapter(db_session, study, "Um", FEN_MATE)
    save_chapter(db_session, um, "Um", "gamebook", "white", arvore_mate())
    create_chapter(db_session, study, "Dois", FEN_PEAO, mode="read")

    copia = duplicate_chapter(db_session, um)

    assert copia.name == "Um (cópia)" and copia.order == 2
    # a cópia teria a mesma posição inicial do original: entra como leitura, sem
    # exercício, e quem duplicou escolhe o modo depois de editá-la
    assert copia.mode == "read" and copia.puzzle_id is None
    assert json.loads(copia.tree_json) == json.loads(db_session.get(StudyChapter, um.id).tree_json)
    db_session.expire_all()
    ordens = [(c.name, c.order) for c in db_session.get(Study, study.id).chapters]
    assert ordens == [("Um", 1), ("Um (cópia)", 2), ("Dois", 3)]


def test_reordenar_os_capitulos(db_session):
    study = estudo_local(db_session)
    ids = [create_chapter(db_session, study, nome).id for nome in ("Um", "Dois", "Três")]

    update_study(db_session, study, chapter_order=[ids[2], ids[0], ids[1]])

    db_session.expire_all()
    capitulos = db_session.get(Study, study.id).chapters
    assert [c.id for c in capitulos] == [ids[2], ids[0], ids[1]]
    assert [c.order for c in capitulos] == [1, 2, 3]


def test_ordem_que_nao_lista_todos_os_capitulos_recusa(db_session):
    study = estudo_local(db_session)
    ids = [create_chapter(db_session, study, nome).id for nome in ("Um", "Dois")]

    with pytest.raises(ChapterOrderError):
        update_study(db_session, study, chapter_order=[ids[0]])
    with pytest.raises(ChapterOrderError):
        update_study(db_session, study, chapter_order=[ids[0], ids[0]])


def test_atualizar_titulo_e_autor(db_session):
    study = estudo_local(db_session, "Antigo", "alguém")

    update_study(db_session, study, title="Novo", author="outro")

    db_session.expire_all()
    atualizado = db_session.get(Study, study.id)
    assert atualizado.title == "Novo" and atualizado.author == "outro"


def test_atualizar_estudo_sem_campo_algum_nao_mexe_no_updated_at(db_session):
    study = estudo_local(db_session, "Antigo", "alguém")
    antes = study.updated_at

    update_study(db_session, study)

    db_session.expire_all()
    atualizado = db_session.get(Study, study.id)
    assert atualizado.updated_at == antes
    assert atualizado.title == "Antigo" and atualizado.author == "alguém"


def test_detalhe_do_capitulo_monta_a_arvore_de_capitulo_antigo(db_session):
    study, _ = importar(db_session, _dois_capitulos())
    chapter = study.chapters[0]
    chapter.tree_json = ""
    db_session.commit()

    dados = chapter_detail(chapter)
    db_session.commit()

    assert dados["tree"]["root"]["children"], dados
    assert dados["fen"] == chapter.fen and dados["pgn"] == chapter.pgn
    assert json.loads(db_session.get(StudyChapter, chapter.id).tree_json) == dados["tree"]
