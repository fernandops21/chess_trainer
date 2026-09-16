import chess
import pytest

from chess_trainer.core.golpes.assinatura import (VERSAO_ASSINATURA, Assinatura, Lance, anotar, assinar, hash64)

# Francesa, avanço: 1.e4 e6 2.d4 d5 3.e5 c5 4.c3 Nc6 5.Nf3 Qb6 6.Bd3 cxd4 7.cxd4 Nxd4 8.Nxd4 Qxd4; brancas jogam 9.Bb5+
FEN_FRANCESA = "r1b1kbnr/pp3ppp/4p3/3pP3/3q4/3B4/PP3PPP/RNBQK2R w KQkq - 0 9"
# Beijo grego: brancas jogam 1.Bxh7+ Kxh7 2.Ng5+ Kg8 3.Qh5
FEN_BEIJO = "r1bq1rk1/pp1nbppp/2p1p3/3pP3/3P4/2PB1N2/PP3PPP/R1BQ1RK1 w - - 0 11"
# Garfo: cavalo branco em d5, rei preto g8, dama preta c8 sem defesa; 1.Ne7+ Kh8 2.Nxc8
FEN_GARFO = "2q3k1/pp3ppp/8/3N4/8/8/PP3PPP/6K1 w - - 0 1"


def test_francesa_anota_o_xeque_que_descobre_a_dama():
    a = assinar(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"])
    assert a.rei == "e8" and a.zona_rei == "centro-fundo"
    b5, xd4 = a.lances
    assert b5 == Lance("B", "d3", "b5", None, "+", None, (("Q", "d4", "d1"),), ())
    assert xd4.peca == "Q" and xd4.destino == "d4" and xd4.captura == "Q" and xd4.xeque == ""
    assert a.destinos() == "Ke8 | B b5 + desc(Qd4) | Q xQ d4"
    assert a.esqueleto() == "Kcentro-fundo | B + desc(Q) | Q xQ"
    assert a.completo() == "Ke8 | B d3-b5 + desc(Qd4<d1) | Q d1-d4 xQ"


def test_beijo_grego():
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5"])
    assert a.destinos() == "Kg8 | B xP h7 + | N g5 + | Q h5"
    assert a.zona_rei == "rei-fundo"


def test_garfo_anota_o_ataque_da_propria_peca():
    a = assinar(FEN_GARFO, ["d5e7", "g8h8", "e7c8"])
    assert a.lances[0].ataques == (("Q", "c8"),) and a.lances[0].xeque == "+"
    assert a.destinos() == "Kg8 | N e7 + atk(Qc8) | N xQ c8"


def test_pretas_a_jogar_da_a_mesma_assinatura_que_brancas():
    # a mesma francesa com as cores trocadas: pretas jogam ...Bb4+ descobrindo a dama de d8 contra d5
    fen_pretas = "rnbqk2r/pp3ppp/3b4/3Q4/3Pp3/4P3/PP3PPP/R1B1KBNR b KQkq - 0 9"
    assert assinar(fen_pretas, ["d6b4", "e1e2", "d8d5"]).destinos() == assinar(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"]).destinos()


def test_xeque_descoberto_duplo_e_mate():
    # rei preto h8, torre branca e1 atrás do bispo e4? monte: bispo em e4 sai com xeque descoberto da torre em e8? Use posição simples:
    # brancas: Ke1? -> usar mate do corredor: 1.Re8# com rei preto g8 e peões f7 g7 h7
    fen_mate = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
    assert assinar(fen_mate, ["e1e8"]).destinos() == "Kg8 | R e8 #"
    # descoberto: bispo em d5 sai e a torre de d1 dá xeque em d8; bispo captura em b7 sem xeque próprio
    fen_desc = "3k4/1p6/8/3B4/8/8/8/3RK3 w - - 0 1"
    assert assinar(fen_desc, ["d5b7"]).lances[0].xeque == "d+"
    # duplo: o cavalo de e4 vai para d6 com xeque e destapa a torre de e1 contra e8
    fen_duplo = "4k3/8/8/8/4N3/8/8/4RK2 w - - 0 1"
    assert assinar(fen_duplo, ["e4d6"]).lances[0].xeque == "++"


def test_peoes_nao_sao_alvo_e_mate_nao_tem_alvos():
    # beijo grego: Ng5+ "ataca" e6 e f7, mas peões não entram; Qxf7# ataca Bf8 e Nf6, mas depois do mate nada entra
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5"])
    assert a.lances[1].ataques == ()
    pastor = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 5 5"
    m = assinar(pastor, ["h5f7"]).lances[0]
    assert m.xeque == "#" and m.ataques == () and m.descobertas == ()


def test_espelho_troca_as_colunas_e_a_zona():
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5"])
    e = a.espelhada()
    assert e.rei == "b8" and e.zona_rei == "dama-fundo"
    assert e.destinos() == "Kb8 | B xP a7 + | N b5 + | Q a5"
    assert a.hashes()["destinos_esp"] == hash64(e.destinos()) and a.hashes()["destinos"] == hash64(a.destinos())


def test_hash64_estavel_e_com_sinal():
    assert hash64("x") == hash64("x") and isinstance(hash64("x"), int) and -2**63 <= hash64("x") < 2**63
    assert hash64("x") != hash64("y")


def test_limita_a_tres_lances_e_ignora_respostas():
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5", "f8e8", "h5h7"])
    assert len(a.lances) == 3


def test_promocao_e_en_passant():
    fen_promo = "8/1P4k1/8/8/8/8/8/4K3 w - - 0 1"
    assert assinar(fen_promo, ["b7b8q"]).destinos() == "Kg7 | P b8 =Q"
    fen_ep = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"
    assert assinar(fen_ep, ["e5d6"]).lances[0].captura == "P"


def test_erros_de_entrada():
    with pytest.raises(ValueError):
        assinar("posicao invalida", ["e2e4"])
    with pytest.raises(ValueError):
        assinar(FEN_BEIJO, ["a1a8"])


def test_anotar_nao_normaliza():
    board = chess.Board("rnbqk2r/pp3ppp/3b4/3Q4/3Pp3/4P3/PP3PPP/R1B1KBNR b KQkq - 0 9")
    a = anotar(board, ["d6b4"])
    assert a.rei == "e1" and a.lances[0].destino == "b4" and VERSAO_ASSINATURA == 1
