import json

import chess
import pytest

from chess_trainer.coach.dossie import montar_dossie
from chess_trainer.coach.tools import ContextoExercicio
from tests.test_coach_tools import FEN, FEN_APOIO, FEN_ERRO, FEN_FATOS_XEQUE, FEN_MATERIAL

SOLUCAO_APOIO = ["Qxf2+", "Kh1", "Qxe1+", "Rxe1", "Nf2+"]


def _contexto(fen=FEN_APOIO, solucao=SOLUCAO_APOIO, fen_erro=None, lance_errado=None, minha_resposta=None, tipo="estudo"):
    return ContextoExercicio(puzzle_id="p1", tipo=tipo, lado="pretas" if " b " in fen else "brancas",
                             fen_inicial=fen, fen_erro=fen_erro, solucao_san=list(solucao), lance_errado=lance_errado,
                             minha_resposta=minha_resposta, partida=None, tema="mate", categoria="rapid")


def analisador(roteiro: dict[str, list[list[str]]] | None = None, falha: str | None = None):
    """Analisador roteirizado que grava cada chamada: `roteiro` dá as continuações (SAN) por FEN;
    fora dele, a primeira jogada legal. `falha` é uma FEN em que a engine "morre"."""
    roteiro = roteiro or {}
    chamadas: list[tuple[str, int]] = []

    def analisar(fen, multipv):
        chamadas.append((fen, multipv))
        if fen == falha:
            raise RuntimeError("engine morreu")
        b = chess.Board(fen)
        if b.is_game_over():
            return {"fen": fen, "turn": "white" if b.turn else "black", "terminal": "checkmate", "lines": []}
        pvs = roteiro.get(fen)
        if pvs is None:
            mv = next(iter(b.legal_moves))
            pvs = [[b.san(mv)]]
        return {"fen": fen, "turn": "white" if b.turn else "black", "terminal": None,
                "lines": [{"move": "", "san": pv[0], "score": 100, "pv": [], "pv_san": list(pv)} for pv in pvs][:multipv]}

    analisar.chamadas = chamadas
    return analisar


def _depois(fen: str, san: str | None = None) -> str:
    b = chess.Board(fen)
    b.push(chess.Move.null() if san is None else b.parse_san(san))
    return b.fen()


def test_dossie_de_um_estudo_analisa_as_quatro_posicoes_e_as_do_erro():
    """O caso real: as pretas jogam Qxf2+; o dossiê traz a posição, as ameaças (lance nulo),
    a posição depois do lance-chave e a segunda linha da engine como defesa natural."""
    analisar = analisador({FEN_APOIO: [SOLUCAO_APOIO, ["Nxb2", "Qxg7#"]]})
    d = montar_dossie(_contexto(fen_erro=FEN_ERRO), analisar)
    assert list(d) == ["inicial", "ameacas_inicial", "fatos_inicial", "apos_solucao", "defesa_natural", "erro", "ameacas_erro", "fatos_erro"]
    # as FENs analisadas, na ordem, com o multipv de cada uma
    assert analisar.chamadas == [(FEN_APOIO, 3), (_depois(FEN_APOIO), 3), (_depois(FEN_APOIO, "Qxf2+"), 2),
                                 (_depois(FEN_APOIO, "Nxb2"), 2), (FEN_ERRO, 3), (_depois(FEN_ERRO), 3)]
    assert d["inicial"]["linhas"][0]["lance"] == "Qxf2+" and d["inicial"]["lado_a_mover"] == "pretas"
    assert d["ameacas_inicial"]["apos_passar"] is True and d["ameacas_inicial"]["quem_ameaca"] == "brancas"
    assert d["fatos_inicial"]["ameacas_do_adversario"]["mates_em_1"] == ["Qxg7#"]
    assert d["fatos_inicial"]["apoios"]["Qxg7#"]["apoiado_por"] == ["Nf5"]
    # depois do lance-chave: o que o adversário tem, com os fatos daquela posição
    assert d["apos_solucao"]["lance"] == "Qxf2+" and d["apos_solucao"]["fen"] == _depois(FEN_APOIO, "Qxf2+")
    assert d["apos_solucao"]["fatos"]["em_xeque"] is True and d["apos_solucao"]["analise"]["lado_a_mover"] == "brancas"
    assert "terminal" not in d["apos_solucao"]
    # sem lance real do aluno, a defesa natural é a segunda linha da engine
    assert d["defesa_natural"]["lance"] == "Nxb2" and d["defesa_natural"]["origem"] == "segunda_linha_da_engine"
    assert d["defesa_natural"]["fen"] == _depois(FEN_APOIO, "Nxb2")
    assert d["defesa_natural"]["analise"]["fen"] == _depois(FEN_APOIO, "Nxb2") and d["defesa_natural"]["fatos"]["lado_a_mover"] == "brancas"
    # a posição do erro ganha as mesmas três seções
    assert d["erro"]["fen"] == FEN_ERRO and d["ameacas_erro"]["apos_passar"] is True and d["fatos_erro"]["lado_a_mover"] == "pretas"
    assert json.loads(json.dumps(d, ensure_ascii=False)) == d


def test_defesa_natural_prefere_a_resposta_do_aluno_na_partida():
    analisar = analisador({FEN: [["Qxf7#"], ["Bxf7+", "Ke7"]]})
    resposta = {"san": "Qxe5+", "uci": "h5e5", "achou": False, "aval_antes": 900, "aval_depois": 100}
    errado = {"san": "Nf6", "uci": "g8f6", "de_quem": "adversário", "nivel": "blunder", "aval_antes": 150, "aval_depois": 900}
    d = montar_dossie(_contexto(fen=FEN, solucao=["Qxf7#"], fen_erro=FEN_ERRO, lance_errado=errado, minha_resposta=resposta, tipo="punir"), analisar)
    assert d["defesa_natural"]["lance"] == "Qxe5+" and d["defesa_natural"]["origem"] == "resposta_do_aluno"
    assert d["defesa_natural"]["fen"] == _depois(FEN, "Qxe5+")
    assert (_depois(FEN, "Qxe5+"), 2) in analisar.chamadas
    # o aluno achou a solução: não há defesa natural a comentar a partir da resposta dele
    achou = {**resposta, "san": "Qxf7#", "achou": True}
    d2 = montar_dossie(_contexto(fen=FEN, solucao=["Qxf7#"], fen_erro=FEN_ERRO, lance_errado=errado, minha_resposta=achou, tipo="punir"),
                       analisador({FEN: [["Qxf7#"], ["Bxf7+", "Ke7"]]}))
    assert d2["defesa_natural"]["lance"] == "Bxf7+" and d2["defesa_natural"]["origem"] == "segunda_linha_da_engine"


def test_defesa_natural_usa_o_lance_errado_do_aluno_quando_o_exercicio_comeca_no_erro():
    analisar = analisador({FEN_MATERIAL: [["Rxd5", "cxd5"], ["Rd1", "Kd8"]]})
    errado = {"san": "Rd3", "uci": "d2d3", "de_quem": "você", "nivel": "blunder", "aval_antes": 400, "aval_depois": -500}
    d = montar_dossie(_contexto(fen=FEN_MATERIAL, solucao=["Rxd5"], fen_erro=FEN_MATERIAL, lance_errado=errado, tipo="evitar"), analisar)
    assert d["defesa_natural"]["lance"] == "Rd3" and d["defesa_natural"]["origem"] == "lance_errado"
    assert d["defesa_natural"]["fen"] == _depois(FEN_MATERIAL, "Rd3")
    # a posição do erro é a própria posição do exercício: as seções do erro não se repetem
    assert not {"erro", "ameacas_erro", "fatos_erro"} & set(d)
    assert list(d) == ["inicial", "ameacas_inicial", "fatos_inicial", "apos_solucao", "defesa_natural"]


def test_defesa_natural_omitida_quando_nao_ha_lance_para_comentar():
    # a engine só tem uma linha
    d = montar_dossie(_contexto(fen=FEN, solucao=["Qxf7#"]), analisador({FEN: [["Qxf7#"]]}))
    assert "defesa_natural" not in d
    # a segunda linha é o próprio lance da solução
    d = montar_dossie(_contexto(fen=FEN, solucao=["Qxf7#"]), analisador({FEN: [["Qxf7#"], ["Qxf7#"]]}))
    assert "defesa_natural" not in d
    # a resposta do aluno não é legal na posição do exercício (dados velhos): não se inventa nada
    ilegal = {"san": "Qxa8", "uci": "h5a8", "achou": False, "aval_antes": 0, "aval_depois": 0}
    d = montar_dossie(_contexto(fen=FEN, solucao=["Qxf7#"], minha_resposta=ilegal, tipo="punir"), analisador({FEN: [["Qxf7#"]]}))
    assert "defesa_natural" not in d
    # o lance errado é do adversário: não é uma defesa que o aluno jogaria
    errado = {"san": "Nf6", "uci": "g8f6", "de_quem": "adversário", "nivel": "blunder", "aval_antes": 150, "aval_depois": 900}
    d = montar_dossie(_contexto(fen=FEN, solucao=["Qxf7#"], fen_erro=FEN_ERRO, lance_errado=errado, tipo="punir"), analisador({FEN: [["Qxf7#"]]}))
    assert "defesa_natural" not in d and "erro" in d


def test_apos_solucao_terminal_nao_pede_analise():
    analisar = analisador({FEN: [["Qxf7#"]]})
    d = montar_dossie(_contexto(fen=FEN, solucao=["Qxf7#"]), analisar)
    assert d["apos_solucao"]["lance"] == "Qxf7#" and d["apos_solucao"]["terminal"] is True
    assert "analise" not in d["apos_solucao"] and d["apos_solucao"]["fatos"]["em_xeque"] is True
    assert (_depois(FEN, "Qxf7#"), 2) not in analisar.chamadas
    # sem solução (ou solução que não bate com a posição), a seção não existe
    assert "apos_solucao" not in montar_dossie(_contexto(fen=FEN, solucao=[]), analisador())
    assert "apos_solucao" not in montar_dossie(_contexto(fen=FEN, solucao=["Qxa8"]), analisador())


def test_em_xeque_as_ameacas_ficam_indisponiveis():
    analisar = analisador()
    d = montar_dossie(_contexto(fen=FEN_FATOS_XEQUE, solucao=["Kxh8"]), analisar)
    assert d["ameacas_inicial"] == {"indisponivel": "em xeque: não dá para passar a vez"}
    assert d["fatos_inicial"]["em_xeque"] is True
    assert all(chess.Board(fen).is_valid() for fen, _ in analisar.chamadas)


def test_engine_que_falha_numa_posicao_derruba_so_aquela_secao():
    analisar = analisador({FEN_APOIO: [SOLUCAO_APOIO, ["Nxb2"]]}, falha=_depois(FEN_APOIO))
    d = montar_dossie(_contexto(), analisar)
    assert d["ameacas_inicial"] == {"erro": "engine morreu"}
    assert d["inicial"]["linhas"][0]["lance"] == "Qxf2+" and d["apos_solucao"]["lance"] == "Qxf2+"
    assert d["defesa_natural"]["lance"] == "Nxb2"
    assert json.loads(json.dumps(d, ensure_ascii=False)) == d
    # FEN que não presta: nenhuma seção calculável, nenhuma exceção
    d = montar_dossie(_contexto(fen="lixo", solucao=["e4"], fen_erro="lixo2"), analisador())
    assert d and all(set(secao) == {"erro"} for secao in d.values())
