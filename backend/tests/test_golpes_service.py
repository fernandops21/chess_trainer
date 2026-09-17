import json

from chess_trainer.config import get_setting
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.service import (
    assinar_lichess,
    assinar_proprio,
    assinatura_de,
    cobertura,
    garantir_assinatura,
    preparar,
)
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleSignature, Position, Puzzle, PuzzleSignature
from tests.factories import make_puzzle
from tests.test_models import _game

# Puzzle do Lichess: `fen` é a posição ANTES do lance de preparação (moves[0]); quem soluciona joga depois dele.
# Aqui: pretas a jogar, o preparo é 8...Qb6xd4?? (toma o cavalo achando o peão de graça) e as brancas
# solucionam com 9.Bb5+ descobrindo a dama de d1 contra d4 — a armadilha da francesa.
FEN_FRANCESA_ANTES = "r1b1kbnr/pp3ppp/1q2p3/3pP3/3N4/3B4/PP3PPP/RNBQK2R b KQkq - 0 8"
MOVES_FRANCESA = "b6d4 d3b5 e8e7 d1d4"
# Mate do pastor: pretas a jogar, preparo 4...Nf6?? e Qxf7#
FEN_PASTOR_ANTES = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 4 4"
MOVES_PASTOR = "g8f6 h5f7"


def lichess(pid: str, fen: str, moves: str, rating: int = 1500, popularity: int = 90):
    return LichessPuzzle(id=pid, fen=fen, moves=moves, rating=rating, rating_deviation=50, popularity=popularity,
                         nb_plays=500, themes="fork", opening_tags="")


def pastor(pid: str, rating: int = 800, popularity: int = 90):
    return lichess(pid, FEN_PASTOR_ANTES, MOVES_PASTOR, rating, popularity)


def test_assinar_lichess_usa_a_posicao_depois_do_preparo(db_session):
    a = assinar_lichess(lichess("frnc1", FEN_FRANCESA_ANTES, MOVES_FRANCESA))
    assert a is not None and a.destinos() == "Ke8 | B b5 + desc(Qd4) | Q xQ d4"
    assert assinar_lichess(lichess("curto", FEN_PASTOR_ANTES, "g8f6")) is None  # menos de dois lances
    assert assinar_lichess(lichess("ilegal", FEN_PASTOR_ANTES, "g8f6 a1a8")) is None  # lance ilegal


def test_garantir_assinatura_grava_e_refaz_por_versao(db_session):
    sol = {"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}
    p = make_puzzle(db_session, fen="r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", solution=sol)
    s = garantir_assinatura(db_session, p)
    assert s is not None and s.versao == VERSAO_ASSINATURA and s.texto_completo == "Ke8 | Q h5-f7 xP #"
    s.versao = 0
    db_session.commit()
    s2 = garantir_assinatura(db_session, p)
    assert s2.versao == VERSAO_ASSINATURA and db_session.query(PuzzleSignature).count() == 1
    assert assinar_proprio(p).destinos() == "Ke8 | Q xP f7 #"


def test_assinatura_de_own_e_lichess(db_session):
    sol = {"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}
    p = make_puzzle(db_session, fen="r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", solution=sol)
    a, fen, lances = assinatura_de(db_session, "own", p.id)
    assert a.destinos() == "Ke8 | Q xP f7 #" and fen == p.fen_start and lances == ["h5f7"]
    db_session.add(lichess("frnc1", FEN_FRANCESA_ANTES, MOVES_FRANCESA)); db_session.commit()
    a2, fen2, lances2 = assinatura_de(db_session, "lichess", "frnc1")
    assert a2.destinos().startswith("Ke8 | B b5 +") and lances2 == ["d3b5", "e8e7", "d1d4"] and fen2.split()[1] == "w"
    assert assinatura_de(db_session, "lichess", "nao-existe") is None


def test_gemeo_adotado_por_capitulo_recalcula_a_assinatura(db_session):
    """Um puzzle de estudo órfão (sem capítulo) com a mesma posição inicial de um capítulo
    novo é adotado por ele (`_upsert_puzzle`, ramo "gêmeo sem dono"); a solução pode ter
    mudado, então a assinatura antiga não pode sobreviver à adoção (achado do fix round 1)."""
    from chess_trainer.core.models import Study, StudyChapter, new_id
    from chess_trainer.core.studies.service import ImportReport, _upsert_puzzle

    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    sol_antiga = {"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}
    orfao = make_puzzle(db_session, fen=fen, kind="punish", solution=sol_antiga)
    orfao.source = "study"
    orfao.chapter_id = None
    db_session.commit()
    antiga = garantir_assinatura(db_session, orfao)
    assert antiga.texto_completo == "Ke8 | Q h5-f7 xP #"

    study = Study(id=new_id(), title="E", author="", source_url="s", origin="local")
    db_session.add(study)
    db_session.flush()
    chapter = StudyChapter(id=new_id(), study_id=study.id, order=1, name="C", fen=fen)
    db_session.add(chapter)
    db_session.flush()

    sol_nova = {"moves": [{"uci": "h5e5", "by": "solver", "alternatives": []}], "explanation_pv": []}
    _upsert_puzzle(db_session, chapter, fen, sol_nova, ImportReport())

    assert chapter.puzzle_id == orfao.id
    atualizado = db_session.get(Puzzle, orfao.id)
    esperado = assinar_proprio(atualizado).completo()
    sig = db_session.get(PuzzleSignature, orfao.id)
    assert sig is not None and sig.texto_completo == esperado and sig.texto_completo != antiga.texto_completo


def test_preparar_assina_em_lotes_e_grava_cobertura(db_session):
    for i in range(7):
        db_session.add(pastor(f"p{i}"))
    db_session.add(lichess("ruim", FEN_PASTOR_ANTES, "g8f6"))  # inválido: fica sem assinatura, sem derrubar a tarefa
    db_session.commit()
    chamadas = []
    n = preparar(db_session, lambda *a: chamadas.append(a), lote=3)
    assert n == 8 and db_session.query(LichessPuzzleSignature).count() == 7
    assert chamadas[-1][0] == "golpes_preparar" and chamadas[-1][1] == chamadas[-1][2]
    cob = get_setting(db_session, "golpes_cobertura", None)
    assert cob["destinos"] == {"ge5": 7, "ge2": 7, "sozinhos": 0} and get_setting(db_session, "golpes_assinados", 0) == 7
    # segunda rodada: nada a fazer
    assert preparar(db_session, lambda *a: None) == 0
    # versão antiga: refaz só ela
    s = db_session.get(LichessPuzzleSignature, "p0"); s.versao = 0; db_session.commit()
    assert preparar(db_session, lambda *a: None) == 1


def test_preparar_para_no_cancelamento(db_session):
    for i in range(6):
        db_session.add(pastor(f"c{i}"))
    db_session.commit()
    vezes = iter([False, True, True])
    n = preparar(db_session, lambda *a: None, should_stop=lambda: next(vezes), lote=2)
    assert n == 2 and db_session.query(LichessPuzzleSignature).count() == 2
    assert get_setting(db_session, "golpes_cobertura", None) is None  # cancelado: cobertura não é gravada


def test_cobertura_conta_grupos_por_nivel(db_session):
    for i in range(5):
        db_session.add(pastor(f"g{i}"))
    db_session.add(lichess("solo", FEN_FRANCESA_ANTES, MOVES_FRANCESA))
    db_session.commit()
    preparar(db_session, lambda *a: None)
    cob = cobertura(db_session)
    assert cob["destinos"] == {"ge5": 5, "ge2": 5, "sozinhos": 1}


def test_persist_draft_grava_assinatura(db_session):
    from chess_trainer.core.puzzles.generator import PuzzleDraft, SolutionMove
    from chess_trainer.core.puzzles.service import persist_draft

    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    game = _game()
    db_session.add(game)
    db_session.flush()
    pos = Position(game_id=game.id, ply=7, fen=fen, move_played="Nc6", move_uci="b8c6",
                   eval_before=0, eval_after=-900, best_move="h5f7", best_eval=900,
                   is_mistake=True, mistake_level="blunder", mistake_by="opponent")
    db_session.add(pos)
    db_session.flush()
    draft = PuzzleDraft(fen_start=fen, side_to_move="white", moves=[SolutionMove("h5f7", "solver")],
                        end_reason="mate", solver_moves=1)
    puzzle = persist_draft(db_session, pos, game, "punish", draft)
    assert puzzle is not None
    assert db_session.get(PuzzleSignature, puzzle.id) is not None
