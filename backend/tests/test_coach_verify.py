import chess

from chess_trainer.coach.verify import SAN_RE, Verificacao, limpar_san, verificar
from chess_trainer.core.evals import MATE_SCORE

# brancas a jogar: Qxf7# é mate; Nf3 e a3 são lances normais
FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
# posição "do erro": as pretas acabaram de jogar Nf6?? (a mesma FEN serve de exemplo)
FEN_ERRO = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"
TEXTO_OK = " ".join(["palavra"] * 80)


def analisar_script(fen: str, multipv: int) -> dict:
    """Engine de mentira: na posição inicial, Qxf7# > Bxf7+ > Nf3; nas outras, um lance qualquer com +0,40 para quem move."""
    board = chess.Board(fen)
    if board.is_checkmate() or board.is_game_over():
        return {"fen": fen, "turn": "white" if board.turn else "black", "terminal": "checkmate", "lines": []}
    if board.fen() == chess.Board(FEN).fen():
        lines = [{"move": "h5f7", "san": "Qxf7#", "score": MATE_SCORE - 1, "pv": ["h5f7"], "pv_san": ["Qxf7#"]},
                 {"move": "c4f7", "san": "Bxf7+", "score": 300, "pv": ["c4f7"], "pv_san": ["Bxf7+"]},
                 {"move": "g1f3", "san": "Nf3", "score": 40, "pv": ["g1f3"], "pv_san": ["Nf3"]}]
        return {"fen": fen, "turn": "white", "terminal": None, "lines": lines[:multipv]}
    mv = next(iter(board.legal_moves))
    return {"fen": fen, "turn": "white" if board.turn else "black", "terminal": None,
            "lines": [{"move": mv.uci(), "san": board.san(mv), "score": 40, "pv": [mv.uci()], "pv_san": [board.san(mv)]}]}


def tipos(v: Verificacao) -> set[str]:
    return {i.tipo for i in v.issues}


def checar(resposta, **kw):
    base = dict(fen_inicial=FEN, fen_erro=FEN_ERRO, lances_permitidos=set(), trechos_ids=set(), analisar=analisar_script)
    base.update(kw)
    return verificar(resposta, **base)


def test_limpar_san_e_regex():
    assert limpar_san("Qxf7#!") == "Qxf7" and limpar_san("O-O-O+") == "O-O-O" and limpar_san("e8=Q+?!") == "e8=Q"
    achados = [m.group(0) for m in SAN_RE.finditer("Depois de 4.Qxf7# acabou; já Nc3x não é lance, e Qd1-h5 tampouco.")]
    assert achados == ["Qxf7#"]


def test_linha_legal_e_principal_passa():
    v = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "avaliacao_cp": None, "mate_em": 0}], "citacoes": []})
    assert v.ok and tipos(v) == set()


def test_lance_ilegal_e_erro():
    v = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"]}]})
    assert not v.ok and tipos(v) == {"lance_ilegal"} and v.issues[0].linha_idx == 0


def test_fora_das_principais_e_aviso_salvo_lance_permitido():
    resposta = {"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["a3"]}]}
    v = checar(resposta)
    assert v.ok and tipos(v) == {"lance_fora_das_principais"}
    v2 = checar(resposta, lances_permitidos={"a2a3"})
    assert tipos(v2) == set()


def test_linha_a_partir_da_posicao_do_erro():
    # das pretas: Nf6 é legal em FEN_ERRO e ilegal em FEN (é a vez das brancas)
    v = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "erro", "lances": ["Nf6", "Qxf7#"], "mate_em": 0}]})
    assert "lance_ilegal" not in tipos(v)
    v2 = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "erro", "lances": ["Nf6"]}]}, fen_erro=None)
    assert "lance_ilegal" in tipos(v2)


def test_avaliacao_conferida_com_tolerancia_de_um_peao():
    # depois de Nf3 é a vez das pretas: a engine dá +0,40 para quem move (pretas) = -0,40 para as brancas
    ok = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": -30}]})
    assert "avaliacao_errada" not in tipos(ok)
    ruim = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": 300}]})
    assert not ruim.ok and "avaliacao_errada" in tipos(ruim)


def test_mate_declarado_confere_com_a_engine():
    assert checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 0}]}).ok
    errado = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 2}]})
    assert not errado.ok and "avaliacao_errada" in tipos(errado)
    # avaliação numérica onde a engine dá mate: aviso, não erro
    numerica = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "avaliacao_cp": 900}]})
    assert numerica.ok and "avaliacao_errada" in tipos(numerica)


def test_avaliacao_nao_numerica_vira_erro_e_nao_excecao():
    string = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": "nao-numerico"}]})
    assert not string.ok and "avaliacao_invalida" in tipos(string)
    lista = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": [1, 2]}]})
    assert not lista.ok and "avaliacao_invalida" in tipos(lista)
    # float é aceito e comparado normalmente, como o -30 inteiro do teste de tolerância
    flutuante = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": -30.0}]})
    assert "avaliacao_invalida" not in tipos(flutuante) and "avaliacao_errada" not in tipos(flutuante)


def test_lance_solto_no_texto_e_aviso():
    v = checar({"texto": TEXTO_OK + " O lance Nc6 defende.", "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 0}]})
    assert v.ok and "lance_sem_linha" in tipos(v)
    v2 = checar({"texto": TEXTO_OK + " O lance Qxf7# decide.", "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 0}]})
    assert "lance_sem_linha" not in tipos(v2)


def test_citacoes():
    ok = checar({"texto": TEXTO_OK + " Veja [c:ab12] no estudo.", "linhas": [], "citacoes": ["ab12"]}, trechos_ids={"ab12"})
    assert ok.ok and "citacao_inexistente" not in tipos(ok) and "citacao_ausente" not in tipos(ok)
    falsa = checar({"texto": TEXTO_OK + " Veja [c:zz99].", "linhas": []}, trechos_ids={"ab12"})
    assert not falsa.ok and "citacao_inexistente" in tipos(falsa)
    sem = checar({"texto": TEXTO_OK + " Como aparece no capítulo três.", "linhas": []})
    assert sem.ok and "citacao_ausente" in tipos(sem)


def test_tamanho_do_texto():
    assert "tamanho" in tipos(checar({"texto": "curto demais", "linhas": []}))
    assert "tamanho" in tipos(checar({"texto": " ".join(["x"] * 401), "linhas": []}))
    assert "tamanho" not in tipos(checar({"texto": TEXTO_OK, "linhas": []}))


def test_engine_fora_do_ar_vira_erro_visivel():
    def quebrada(fen, multipv):
        raise RuntimeError("engine indisponível")
    v = verificar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": 0}]},
                  fen_inicial=FEN, fen_erro=None, lances_permitidos=set(), trechos_ids=set(), analisar=quebrada)
    assert not v.ok and tipos(v) == {"engine_indisponivel"}
    assert v.to_dict()["ok"] is False and v.to_dict()["issues"][0]["tipo"] == "engine_indisponivel"
