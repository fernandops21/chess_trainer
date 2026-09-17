"""Tabelas de assinatura do golpe, trechos, rótulos do conjunto de ouro e vínculo
sibling_of/sibling_tier entre exercícios (spec golpes §4, §6, §8, trechos §3.5)."""

from chess_trainer.core.models import (
    GolpeLabel, LichessPuzzle, LichessPuzzleSignature, LichessPuzzleTrecho, Puzzle, PuzzleSignature,
)
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
    irmao.sibling_tier = "trecho2"
    db_session.add(PuzzleSignature(puzzle_id=origem.id, versao=1, esqueleto=1, destinos=2, destinos_esp=3, completo=4,
                                   texto_completo="x", zona_rei="centro-fundo", n_lances=1))
    db_session.add(GolpeLabel(anchor_origem="own", anchor_id=origem.id, candidate_id="abcde", tier_na_hora="mesmo",
                              versao_assinatura=1, label="mesmo", n_lances=2, posicao="inicio", nivel="destinos",
                              espelhado=False))
    db_session.commit()
    assert db_session.get(LichessPuzzleSignature, "abcde").destinos == 2
    assert db_session.get(Puzzle, irmao.id).sibling_of == origem.id
    assert db_session.get(Puzzle, irmao.id).sibling_tier == "trecho2"
    rotulo = db_session.query(GolpeLabel).one()
    assert rotulo.label == "mesmo" and rotulo.n_lances == 2 and rotulo.posicao == "inicio"
    assert rotulo.nivel == "destinos" and rotulo.espelhado is False


def test_tabela_de_trechos(db_session):
    db_session.add(LichessPuzzle(id="abcde", fen=FEN, moves="a2a3 h5f7 g8f6 f7f6", rating=1200, rating_deviation=50,
                                 popularity=90, nb_plays=500, themes="mate", opening_tags=""))
    db_session.commit()
    db_session.add(LichessPuzzleTrecho(puzzle_id="abcde", inicio=0, n=1, posicao="inicio", destinos=10,
                                       destinos_esp=20, esqueleto=None))
    db_session.add(LichessPuzzleTrecho(puzzle_id="abcde", inicio=0, n=2, posicao="inteira", destinos=30,
                                       destinos_esp=40, esqueleto=50))
    db_session.commit()
    linhas = db_session.query(LichessPuzzleTrecho).order_by(LichessPuzzleTrecho.n).all()
    assert [(l.inicio, l.n, l.posicao, l.esqueleto) for l in linhas] == [
        (0, 1, "inicio", None), (0, 2, "inteira", 50),
    ]
    # ondelete CASCADE: apagar o puzzle do Lichess apaga os trechos dele
    db_session.delete(db_session.get(LichessPuzzle, "abcde"))
    db_session.commit()
    assert db_session.query(LichessPuzzleTrecho).count() == 0
