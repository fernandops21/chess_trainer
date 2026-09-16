import json

from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.service import assinar_lichess, assinar_proprio, assinatura_de, garantir_assinatura
from chess_trainer.core.models import LichessPuzzle, Position, PuzzleSignature
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
