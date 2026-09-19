import json
from pathlib import Path

import chess

from chess_trainer.core.golpes.mates import (
    NOME_PT, PADROES, corredor_apertado, padrao_de_mate, padrao_do_exercicio, padrao_para_candidato,
)

FIXTURE = Path(__file__).parent / "data" / "mates_lichess_amostra.json"
TEMAS_APROVADOS = ("smotheredMate", "arabianMate", "backRankMate")
# a ordem de PADROES é do mais específico ao mais geral: quando uma posição bate com mais de
# um padrão, `padrao_de_mate` sempre acha o mais específico primeiro
ESPECIFICIDADE = {nome: i for i, (nome, _detector) in enumerate(PADROES)}


def _final(fen: str, lances_uci) -> chess.Board:
    b = chess.Board(fen)
    for u in lances_uci:
        b.push(chess.Move.from_uci(u))
    return b


# --- corredor (mate do corredor) ---------------------------------------------

FEN_CORREDOR = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"


def test_corredor_positivo():
    assert padrao_de_mate(_final(FEN_CORREDOR, ["e1e8"])) == "backRankMate"


def test_a_linha_do_usuario_e_um_corredor():
    """36.Rb8+ Qd8 37.Rxd8+ Ne8 38.Rxe8#, a posição REAL do exercício que motivou o degrau: peões
    em f7 e g7, h7 vazia (o peão está em h6) e coberta de longe pela dama de d3. Para o jogador é
    mate do corredor; a regra tolera uma casa vazia à frente do rei quando o adversário a cobre."""
    fen = "6k1/5pp1/5n1p/2pqp3/r1N5/2PQ1P1P/6P1/1R4K1 w - - 0 36"
    lances = ["b1b8", "d5d8", "b8d8", "f6e8", "d8e8"]
    assert padrao_do_exercicio(fen, lances) == ("backRankMate", 3)


def test_corredor_tolera_uma_casa_coberta_e_so_uma():
    import chess
    from chess_trainer.core.golpes.mates import padrao_de_mate
    # h7 vazia e coberta pelo bispo de d3: corredor
    assert padrao_de_mate(chess.Board("4R1k1/5pp1/8/8/8/3B4/8/6K1 b - - 0 1")) == "backRankMate"
    # g7 e h7 vazias, as duas cobertas (bispo em d3 cobre h7, dama em a1 cobre g7): mate, mas
    # com duas casas só cobertas já não é "rei preso atrás dos próprios peões"
    b = chess.Board("4R1k1/5p2/8/8/8/3B4/8/Q5K1 b - - 0 1")
    assert b.is_checkmate() and padrao_de_mate(b) is None


# --- corredor apertado (etiqueta própria, spec golpes design §3.6/§4) --------


def _detectar_apertado(board: chess.Board) -> bool:
    dono = board.turn
    rei = board.king(dono)
    xeques = list(board.checkers())
    return corredor_apertado(board, rei, dono, xeques)


def test_corredor_apertado_textbook_dama():
    """`Qe8#` contra um rei fechado só por peões em f7/g7/h7: textbook, aprovado na amostra
    inspecionada à mão (4 451 extras do corpus do Lichess, spec golpes design §3.6)."""
    board = chess.Board("4Q1k1/3p1ppp/8/8/8/8/8/6K1 b - - 0 1")
    assert board.is_valid() and board.is_checkmate()
    assert _detectar_apertado(board) is True
    assert padrao_para_candidato(board) == "backRankMate"


def test_corredor_apertado_textbook_torre():
    """`Rf8#` com o rei em h8 atrás de g7/h7: o outro textbook citado na spec."""
    board = chess.Board("5R1k/6pp/8/8/8/8/8/6K1 b - - 0 1")
    assert board.is_valid() and board.is_checkmate()
    assert _detectar_apertado(board) is True
    assert padrao_para_candidato(board) == "backRankMate"


def test_corredor_apertado_nega_peca_nao_peao_na_frente():
    """Mate real, mas a casa f7 é ocupada por uma TORRE (presa pela cravada do bispo de d5), não
    por um peão: a regra frouxa (qualquer peça própria) contava isso como corredor — metade dos
    9 224 extras eram assim, e a regra apertada os rejeita."""
    board = chess.Board("4R1k1/5rpp/8/3B4/8/8/8/6K1 b - - 0 1")
    assert board.is_valid() and board.is_checkmate()
    assert _detectar_apertado(board) is False
    assert padrao_para_candidato(board) is None
    # a regra tolerante do exercício do usuário, ao contrário, aceita (qualquer peça própria)
    assert padrao_de_mate(board) == "backRankMate"


def test_corredor_apertado_nega_torre_dama_adjacente():
    """Torre/dama adjacente ao rei não conta: seria outro padrão (o corredor exige a peça
    atacando de longe pela última fila, não encostada)."""
    board = chess.Board("6Qk/6pp/8/8/2B5/8/8/K7 b - - 0 1")
    assert board.is_valid() and board.is_checkmate()
    assert _detectar_apertado(board) is False


def test_corredor_apertado_nega_a_posicao_real_do_usuario():
    """A posição real do exercício (h7 vazia, coberta de longe pela dama): a regra tolerante
    (`corredor`) aceita, a apertada não — ela nunca classifica o exercício do usuário, só gera
    etiqueta própria para o Lichess."""
    fen = "6k1/5pp1/5n1p/2pqp3/r1N5/2PQ1P1P/6P1/1R4K1 w - - 0 36"
    board = chess.Board(fen)
    for uci in ["b1b8", "d5d8", "b8d8", "f6e8", "d8e8"]:
        board.push(chess.Move.from_uci(uci))
    assert board.is_checkmate()
    assert padrao_de_mate(board) == "backRankMate"
    assert _detectar_apertado(board) is False
    assert padrao_para_candidato(board) is None


def test_corredor_apertado_nega_duas_casas_cobertas():
    """A mesma posição do near-miss de `corredor` (duas casas vazias, cobertas a distância): a
    regra apertada nega junto com a tolerante."""
    board = chess.Board("4R1k1/5p2/8/8/8/3B4/8/Q5K1 b - - 0 1")
    assert board.is_checkmate()
    assert _detectar_apertado(board) is False


def test_padrao_para_candidato_fora_do_xeque_mate_e_none():
    assert padrao_para_candidato(chess.Board(chess.STARTING_FEN)) is None


# --- sufocado (mate sufocado) ------------------------------------------------

FEN_SUFOCADO = "6rk/5Npp/8/8/8/8/8/6K1 b - - 0 1"


def test_sufocado_positivo():
    assert padrao_de_mate(chess.Board(FEN_SUFOCADO)) == "smotheredMate"


def test_sufocado_quase_com_uma_casa_livre():
    """Cavalo dando xeque só, mas uma casa ao redor do rei (g7) está vazia — coberta por um
    bispo a distância, não ocupada por peça própria: near-miss do sufocado."""
    fen = "6rk/7p/6N1/8/8/8/1B6/K7 b - - 0 1"
    board = chess.Board(fen)
    assert board.is_checkmate()
    assert padrao_de_mate(board) is None


# --- árabe (mate árabe) -------------------------------------------------------

FEN_ARABE = "7k/7R/5N2/8/8/8/8/K7 b - - 0 1"


def test_arabe_positivo():
    assert padrao_de_mate(chess.Board(FEN_ARABE)) == "arabianMate"


def test_arabe_quase_sem_apoio_do_cavalo():
    """Torre no canto dando xeque adjacente, mas apoiada por um bispo, não por um cavalo (as
    outras casas de fuga ficam bloqueadas pelas próprias peças do rei) — near-miss do árabe."""
    fen = "6rk/6pR/8/8/8/8/2B5/K7 b - - 0 1"
    board = chess.Board(fen)
    assert board.is_checkmate()
    assert padrao_de_mate(board) is None


# --- fora do xeque-mate --------------------------------------------------------


def test_fora_do_xeque_mate_e_none():
    assert padrao_de_mate(chess.Board(chess.STARTING_FEN)) is None


def test_nome_pt_cobre_os_tres_padroes():
    assert set(NOME_PT) == set(TEMAS_APROVADOS)


def test_padrao_do_exercicio_fen_invalida_ou_lance_ilegal_nunca_levanta():
    assert padrao_do_exercicio("posicao invalida", ["e2e4"]) is None
    assert padrao_do_exercicio(FEN_CORREDOR, ["a1a8"]) is None
    assert padrao_do_exercicio(FEN_CORREDOR, ["zz99"]) is None


def test_padrao_do_exercicio_sem_mate_e_none():
    # 1.e4: não termina em xeque-mate
    assert padrao_do_exercicio(chess.STARTING_FEN, ["e2e4"]) is None


# --- fixture do Lichess (240 mates reais: 40 de cada padrão aprovado, 120 outros) --------


def _fixture():
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def test_recall_100_por_padrao_na_amostra_do_lichess():
    """Para todo puzzle do Lichess etiquetado com um dos três padrões aprovados,
    `padrao_de_mate` da posição final acha ESSE padrão ou um mais específico que a posição
    também satisfaça (a regra sempre acha o mais específico primeiro) — recall 100% por tema,
    a régua de aprovação de um detector (spec golpes design §3.6)."""
    dados = _fixture()
    for item in dados:
        temas = set(item["themes"].split())
        for tema in TEMAS_APROVADOS:
            if tema not in temas:
                continue
            detectado = padrao_de_mate(_final(item["fen"], item["moves"].split()))
            assert detectado is not None, (item["id"], tema)
            assert ESPECIFICIDADE[detectado] <= ESPECIFICIDADE[tema], (item["id"], tema, detectado)


def test_precisao_100_do_sufocado_nos_outros_mates_da_amostra():
    """Nos 120 mates da amostra sem nenhum dos três temas: nenhum é classificado sufocado
    (precisão 100% medida para esse padrão). Corredor e árabe têm extras esperados
    (estruturalmente corretos, mas sem a etiqueta do Lichess) e não entram nesta conta."""
    dados = _fixture()
    outros = [item for item in dados if not set(item["themes"].split()) & set(TEMAS_APROVADOS)]
    assert len(outros) == 120
    for item in outros:
        detectado = padrao_de_mate(_final(item["fen"], item["moves"].split()))
        assert detectado != "smotheredMate", item["id"]
