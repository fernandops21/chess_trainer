"""Tabelas de assinatura do golpe, rótulos do conjunto de ouro e vínculo
sibling_of entre exercícios (spec golpes §4, §6, §8)."""

from chess_trainer.core.models import GolpeLabel, LichessPuzzle, LichessPuzzleSignature, Puzzle, PuzzleSignature
from tests.factories import make_puzzle

FEN = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"


def test_tabelas_de_assinatura_e_vinculo_de_irmao(db_session):
    db_session.add(LichessPuzzle(id="abcde", fen=FEN, moves="a2a3 h5f7", rating=1200, rating_deviation=50,
                                 popularity=90, nb_plays=500, themes="mate", opening_tags=""))
    db_session.add(LichessPuzzleSignature(puzzle_id="abcde", versao=1, esqueleto=1, destinos=2, destinos_esp=3, completo=4,
                                          texto_completo="Ke8 | Q xP f7 #", zona_rei="centro-fundo", n_lances=1))
    origem = make_puzzle(db_session, fen=FEN)
    irmao = make_puzzle(db_session, fen=FEN.replace("w", "b"), side="black")
    irmao.sibling_of = origem.id
    db_session.add(PuzzleSignature(puzzle_id=origem.id, versao=1, esqueleto=1, destinos=2, destinos_esp=3, completo=4,
                                   texto_completo="x", zona_rei="centro-fundo", n_lances=1))
    db_session.add(GolpeLabel(anchor_origem="own", anchor_id=origem.id, candidate_id="abcde", tier_na_hora="mesmo",
                              versao_assinatura=1, label="mesmo"))
    db_session.commit()
    assert db_session.get(LichessPuzzleSignature, "abcde").destinos == 2
    assert db_session.get(Puzzle, irmao.id).sibling_of == origem.id
    assert db_session.query(GolpeLabel).one().label == "mesmo"
