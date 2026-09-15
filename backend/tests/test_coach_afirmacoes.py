import json

import chess

from chess_trainer.coach.afirmacoes import ESQUEMA_AFIRMACOES, SYSTEM_AFIRMACOES, conferir_afirmacoes, extrair_afirmacoes
from chess_trainer.coach.costs import Uso
from chess_trainer.coach.llm import FERRAMENTA_FINAL
from chess_trainer.coach.verify import _posicoes_alcancaveis
from tests.fakes import FakeLlm

# caso real: pretas a jogar; só o cavalo de f5 ataca d4 (o bispo de f4 tapa a dama de g4), e as
# pretas defendem d4 duas vezes (cavalo de c6 e torre de d8)
FEN = "3r1rk1/1pp1bppp/p1n5/4PN2/3q1BQ1/2Nn4/PP3PPP/R3R1K1 b - - 0 1"
# a solução: 1...Qxf2+ 2.Kh1 (único lance) Qxe1+ 3.Rxe1 Nf2+ (garfo em h1 e g4)
LINHA = {"inicio": "inicial", "lances": ["Qxf2+", "Kh1", "Qxe1+", "Rxe1", "Nf2+"], "avaliacao_cp": None, "mate_em": None}
# mate do pastor, brancas a jogar: o rei de e1 tem duas casas (f1 e e2)
FEN_PASTOR = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"


def afirmacao(tipo, trecho="trecho", **campos):
    base = {"tipo": tipo, "trecho": trecho, "peca": None, "alvo": None, "lance": None, "lado": None, "tipo_peca": None, "casas": []}
    return {**base, **campos}


def conferir(*afirmacoes, fen=FEN, linhas=(LINHA,)):
    return conferir_afirmacoes(list(afirmacoes), _posicoes_alcancaveis(fen, None, list(linhas)))


def falsas(*afirmacoes, **kw) -> list[str]:
    issues = conferir(*afirmacoes, **kw)
    assert all(i.tipo == "afirmacao_falsa" and i.gravidade == "erro" for i in issues)
    return [i.detalhe for i in issues]


def test_esquema_e_estrito_e_sem_palavras_que_a_api_recusa():
    texto = json.dumps(ESQUEMA_AFIRMACOES)
    assert "minItems" not in texto and "maxItems" not in texto
    assert ESQUEMA_AFIRMACOES["additionalProperties"] is False and ESQUEMA_AFIRMACOES["required"] == ["afirmacoes"]
    item = ESQUEMA_AFIRMACOES["properties"]["afirmacoes"]["items"]
    assert item["additionalProperties"] is False
    assert sorted(item["required"]) == sorted(item["properties"]) == sorted(["tipo", "trecho", "peca", "alvo", "lance", "lado", "tipo_peca", "casas"])
    assert set(item["properties"]["tipo"]["enum"]) == {"ataca", "mais_atacantes", "indefesa", "cravada", "unico_lance", "unica_casa_do_rei",
                                                         "garfo", "xeque", "mate", "peca_em_casa", "outro"}
    for campo in ("peca", "alvo", "lance", "lado", "tipo_peca"):
        assert item["properties"][campo]["type"] == ["string", "null"], campo
    assert item["properties"]["casas"]["type"] == "array"
    # o extrator entrega pela mesma ferramenta final que o cliente já força
    assert FERRAMENTA_FINAL in SYSTEM_AFIRMACOES and "mais_atacantes" in SYSTEM_AFIRMACOES and "outro" in SYSTEM_AFIRMACOES


def test_extrair_devolve_a_lista_o_uso_e_as_chamadas():
    lista = [afirmacao("ataca", "a dama de g4 ataca d4", peca="g4", alvo="d4")]
    llm = FakeLlm([[("final", {"afirmacoes": lista})]], uso=Uso(300, 50, 0, 0))
    afirmacoes, uso, n = extrair_afirmacoes(llm, "A dama de g4 ataca d4.")
    assert afirmacoes == lista and uso == Uso(300, 50, 0, 0) and n == 1
    # barato: sem ferramentas, esforço baixo, teto curto, e o texto vai na mensagem
    p = llm.prompts[0]
    assert p["ferramentas"] == [] and p["effort"] == "low" and p["max_tokens"] == 4000
    assert p["system"] == SYSTEM_AFIRMACOES and "A dama de g4 ataca d4." in p["user"]


def test_extrair_sem_resposta_estruturada_devolve_lista_vazia():
    afirmacoes, uso, n = extrair_afirmacoes(FakeLlm([[("texto", "não sei")]]), "texto")
    assert afirmacoes == [] and uso == Uso(1000, 200, 500, 0) and n == 1
    # lista malformada também não derruba: só os dicionários contam
    llm = FakeLlm([[("final", {"afirmacoes": ["x", afirmacao("outro")]})]])
    assert extrair_afirmacoes(llm, "texto")[0] == [afirmacao("outro")]
    assert extrair_afirmacoes(FakeLlm([[("final", {"afirmacoes": "nada"})]]), "texto")[0] == []


def test_ataca_o_caso_real_da_dama_de_g4():
    detalhes = falsas(afirmacao("ataca", "a dama de g4 ataca d4", peca="g4", alvo="d4"))
    assert len(detalhes) == 1 and detalhes[0].startswith("«a dama de g4 ataca d4»") and "f5" in detalhes[0] and "g4 não ataca d4" in detalhes[0]
    assert falsas(afirmacao("ataca", "o cavalo de f5 ataca d4", peca="f5", alvo="d4")) == []
    # a peça que só existe depois de um lance da linha também vale: a dama chega a f2 em Qxf2+
    assert falsas(afirmacao("ataca", "a dama de f2 ataca g1", peca="f2", alvo="g1")) == []
    # casa sem peça em nenhuma posição
    assert "não há peça em a5" in falsas(afirmacao("ataca", "x", peca="a5", alvo="d4"))[0]


def test_mais_atacantes_conta_os_dois_lados():
    detalhes = falsas(afirmacao("mais_atacantes", "as brancas atacam d4 mais vezes do que as pretas defendem", lado="brancas", alvo="d4"))
    assert len(detalhes) == 1 and "1" in detalhes[0] and "2" in detalhes[0] and "brancas" in detalhes[0] and "pretas" in detalhes[0]
    assert falsas(afirmacao("mais_atacantes", "x", lado="pretas", alvo="d4")) == []


def test_unico_lance_e_unica_casa_do_rei():
    # depois de 1...Qxf2+ o único lance das brancas é Kh1
    assert falsas(afirmacao("unica_casa_do_rei", "Kh1 é a única casa do rei", lance="Kh1")) == []
    assert falsas(afirmacao("unico_lance", "Kh1 é forçado", lance="Kh1")) == []
    # no mate do pastor o rei tem duas casas
    detalhes = falsas(afirmacao("unica_casa_do_rei", "Kf1 é a única casa", lance="Kf1"), fen=FEN_PASTOR, linhas=())
    assert len(detalhes) == 1 and "Kf1 não é o único lance do rei" in detalhes[0] and "Ke2" in detalhes[0]
    detalhes = falsas(afirmacao("unico_lance", "Qxf7# é o único lance", lance="Qxf7#"), fen=FEN_PASTOR, linhas=())
    assert len(detalhes) == 1 and "não é o único lance" in detalhes[0]
    # lance que não é do rei, ou que não é legal em posição nenhuma
    assert "não é lance do rei" in falsas(afirmacao("unica_casa_do_rei", "x", lance="Qxf7#"), fen=FEN_PASTOR, linhas=())[0]
    assert "não é legal" in falsas(afirmacao("unica_casa_do_rei", "x", lance="Kh8"), fen=FEN_PASTOR, linhas=())[0]


def test_indefesa_e_cravada():
    # a dama de g4 não tem defensor; o cavalo de f5 é defendido pela dama
    assert falsas(afirmacao("indefesa", "a dama de g4 está indefesa", peca="g4")) == []
    detalhes = falsas(afirmacao("indefesa", "o cavalo de f5 está indefeso", peca="f5"))
    assert len(detalhes) == 1 and "f5" in detalhes[0] and "g4" in detalhes[0]
    # o peão de f2 está cravado pela dama de d4 contra o rei de g1; o bispo de e7 não está cravado
    assert falsas(afirmacao("cravada", "o peão de f2 está cravado", peca="f2")) == []
    detalhes = falsas(afirmacao("cravada", "o bispo de e7 está cravado", peca="e7"))
    assert len(detalhes) == 1 and "e7 não está cravada" in detalhes[0]


def test_garfo_xeque_mate_e_peca_em_casa():
    # depois de 3...Nf2+ o cavalo ataca h1 (o rei) e g4 (a dama)
    assert falsas(afirmacao("garfo", "Nf2+ garfa rei e dama", peca="f2", casas=["h1", "g4"])) == []
    detalhes = falsas(afirmacao("garfo", "o cavalo de f5 garfa d4 e d8", peca="f5", casas=["d4", "d8"]))
    assert len(detalhes) == 1 and "d8" in detalhes[0] and "f5" in detalhes[0]
    assert falsas(afirmacao("xeque", "Qxf2+", lance="Qxf2+")) == []
    assert "não dá xeque" in falsas(afirmacao("xeque", "Nxb2+", lance="Nxb2+"))[0]
    assert falsas(afirmacao("mate", "Qxf7#", lance="Qxf7#"), fen=FEN_PASTOR, linhas=()) == []
    assert "não é mate" in falsas(afirmacao("mate", "Qxf2#", lance="Qxf2#"))[0]
    assert falsas(afirmacao("peca_em_casa", "a torre de d8", peca="d8", tipo_peca="torre", lado="pretas")) == []
    assert falsas(afirmacao("peca_em_casa", "a dama de g4", peca="g4", tipo_peca="dama")) == []
    assert "não há dama das pretas em g4" in falsas(afirmacao("peca_em_casa", "x", peca="g4", tipo_peca="dama", lado="pretas"))[0]
    assert "não há bispo em f6" in falsas(afirmacao("peca_em_casa", "x", peca="f6", tipo_peca="bispo"))[0]


def test_outro_malformado_e_duplicatas():
    assert conferir(afirmacao("outro", "as brancas estão melhor")) == []
    # casa inválida, campo faltando, garfo com uma casa só, lance vazio, tipo desconhecido: ignorados
    assert conferir(afirmacao("ataca", "x", peca="z9", alvo="d4"), afirmacao("ataca", "x", peca="g4"),
                    afirmacao("garfo", "x", peca="f5", casas=["d4"]), afirmacao("xeque", "x", lance=""),
                    afirmacao("mais_atacantes", "x", lado="verdes", alvo="d4"), afirmacao("inventado", "x"),
                    {"tipo": "ataca"}, "não sou dicionário") == []
    # sem posição alcançável não há o que conferir
    assert conferir_afirmacoes([afirmacao("ataca", "x", peca="g4", alvo="d4")], []) == []
    # a mesma afirmação falsa duas vezes rende um erro só
    a = afirmacao("ataca", "a dama de g4 ataca d4", peca="g4", alvo="d4")
    assert len(conferir(a, dict(a))) == 1


def test_posicoes_da_resposta_e_a_mesma_lista_do_verificador():
    from chess_trainer.coach.verify import posicoes_da_resposta
    resposta = {"linhas": [LINHA]}
    de_la = [b.fen() for b in posicoes_da_resposta(resposta, fen_inicial=FEN, fen_erro=None)]
    assert de_la == [b.fen() for b in _posicoes_alcancaveis(FEN, None, [LINHA])] and len(de_la) == 7
    assert chess.Board(FEN).fen() == de_la[0]
