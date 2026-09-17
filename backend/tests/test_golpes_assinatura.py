import hashlib

import chess
import pytest

from chess_trainer.core.golpes.assinatura import (VERSAO_ASSINATURA, Assinatura, Lance, anotar, assinar, hash64, trechos)

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
    # pino contra deriva do algoritmo: os 8 primeiros bytes do BLAKE2b (spec §3.4)
    assert hash64("x") == int.from_bytes(hashlib.blake2b(b"x").digest()[:8], "big", signed=True)


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
    assert a.rei == "e1" and a.lances[0].destino == "b4" and VERSAO_ASSINATURA == 2


# --- trechos (spec golpes trechos §3.5) --------------------------------------


def test_trechos_da_francesa_inicio_inteira_e_fim():
    ts = {(t.inicio, t.n): t for t in trechos(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"])}
    assert set(ts) == {(0, 1), (0, 2), (1, 1)}
    assert ts[(0, 1)].posicao == "inicio" and ts[(0, 1)].assinatura.destinos() == "Ke8 | B b5 + desc(Qd4)"
    assert ts[(0, 2)].posicao == "inteira" and ts[(0, 2)].assinatura.destinos() == "Ke8 | B b5 + desc(Qd4) | Q xQ d4"
    # o rei segue a peça: o trecho "fim" começa depois do rei fugir para e7
    assert ts[(1, 1)].posicao == "fim" and ts[(1, 1)].assinatura.destinos() == "Ke7 | Q xQ d4"


def test_trecho_de_tres_lances_da_um_trecho_do_meio():
    ts = {(t.inicio, t.n): t for t in trechos(FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5"])}
    assert ts[(1, 1)].posicao == "meio"
    assert ts[(0, 3)].posicao == "inteira" and ts[(0, 1)].posicao == "inicio"
    assert ts[(1, 2)].posicao == "fim" and ts[(2, 1)].posicao == "fim"


def test_trechos_pretas_igual_a_brancas():
    fen_pretas = "rnbqk2r/pp3ppp/3b4/3Q4/3Pp3/4P3/PP3PPP/R1B1KBNR b KQkq - 0 9"
    a = {(t.inicio, t.n): t.assinatura.destinos() for t in trechos(fen_pretas, ["d6b4", "e1e2", "d8d5"])}
    b = {(t.inicio, t.n): t.assinatura.destinos() for t in trechos(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"])}
    assert a == b


def test_trechos_respeita_max_solver():
    # sete lances: quatro do solucionador (d3b5 é só o primeiro de uma solução mais longa fictícia)
    fen_mate = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
    ts = trechos(fen_mate, ["e1e8"], max_solver=0)
    assert ts == []


def test_trechos_levanta_erro_como_assinar():
    with pytest.raises(ValueError):
        trechos("posicao invalida", ["e2e4"])
    with pytest.raises(ValueError):
        trechos(FEN_BEIJO, ["a1a8"])


def _trechos_de_referencia(fen, lances, max_solver=6):
    """A definição, do jeito lento: um `anotar` por (início, tamanho)."""
    import chess as _c
    from chess_trainer.core.golpes.assinatura import _uci_espelho_vertical
    board = _c.Board(fen)
    if board.turn == _c.BLACK:
        board = board.mirror()
        lances = [_uci_espelho_vertical(u) for u in lances]
    n_solver = (len(lances) + 1) // 2
    limite = min(n_solver, max_solver)
    out = []
    b = board.copy()
    for i in range(limite):
        for n in (1, 2, 3):
            if i + n <= limite:
                out.append((i, n, anotar(b, lances[2 * i:], max_lances=n)))
        for u in lances[2 * i:2 * i + 2]:
            b.push(_c.Move.from_uci(u))
    return out


def test_trechos_em_uma_passada_batem_com_a_definicao():
    from chess_trainer.core.golpes.assinatura import assinar_com_trechos, trechos
    casos = [
        (FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"]),
        (FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5", "f8e8", "h5h7"]),
        ("rnbqk2r/pp3ppp/3b4/3Q4/3Pp3/4P3/PP3PPP/R1B1KBNR b KQkq - 0 9", ["d6b4", "e1e2", "d8d5"]),
        (FEN_GARFO, ["d5e7", "g8h8", "e7c8"]),
    ]
    for fen, lances in casos:
        rapido = [(t.inicio, t.n, t.assinatura) for t in trechos(fen, lances)]
        assert rapido == _trechos_de_referencia(fen, lances)
        a, ts = assinar_com_trechos(fen, lances)
        assert a == assinar(fen, lances) and ts == trechos(fen, lances)
