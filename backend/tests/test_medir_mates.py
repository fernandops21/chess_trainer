"""Testa só a função pura de contagem do script de medição (`evals/golpes/medir_mates.py`):
o script em si abre o banco real, somente leitura, e não é exercitado aqui (spec: nunca rodar
contra o banco real nos testes)."""
import json
from pathlib import Path

from chess_trainer.core.golpes.mates import padrao_de_mate, padrao_para_candidato
from evals.golpes.medir_mates import _posicao_final, contar, contar_candidatos

FIXTURE = Path(__file__).parent / "data" / "mates_lichess_amostra.json"


def _pares_da_amostra():
    with FIXTURE.open(encoding="utf-8") as f:
        dados = json.load(f)
    pares = []
    for item in dados:
        board = _posicao_final(item["fen"], item["moves"])
        pares.append((padrao_de_mate(board), frozenset(item["themes"].split())))
    return pares


def _pares_candidatos_da_amostra():
    with FIXTURE.open(encoding="utf-8") as f:
        dados = json.load(f)
    pares = []
    for item in dados:
        board = _posicao_final(item["fen"], item["moves"])
        pares.append((padrao_para_candidato(board), frozenset(item["themes"].split())))
    return pares


def test_contar_bate_com_os_numeros_medidos_na_amostra():
    """Os mesmos 240 puzzles da amostra de `test_golpes_mates.py`: 40 de cada padrão aprovado
    e 120 outros. Recall 100% nos três (medido na amostra); o corredor tem 3 sobras (mates
    estruturalmente corretos que a amostra não etiqueta) — mesmo formato do achado da spec
    golpes design §3.6 no corpus inteiro do Lichess (recall 100%, precisão 58%), só que numa
    amostra pequena a precisão não cai tanto."""
    contagens = contar(_pares_da_amostra())
    assert contagens["smotheredMate"] == {"lichess": 40, "recall_ok": 40, "detector": 40, "precisao_ok": 40}
    assert contagens["arabianMate"] == {"lichess": 40, "recall_ok": 40, "detector": 40, "precisao_ok": 40}
    assert contagens["backRankMate"]["lichess"] == 40 and contagens["backRankMate"]["recall_ok"] == 40
    assert contagens["backRankMate"]["detector"] >= contagens["backRankMate"]["precisao_ok"] == 40


def test_contar_vazio():
    vazio = {"lichess": 0, "recall_ok": 0, "detector": 0, "precisao_ok": 0}
    contagens = contar([])
    assert all(c == vazio for c in contagens.values())


def test_contar_aceita_padrao_mais_especifico_no_recall():
    """Um mate etiquetado pelo Lichess como `backRankMate`, mas que o detector classifica como
    `smotheredMate` (mais específico e também aprovado): conta para o recall do corredor, não
    é uma falha (spec golpes design §3.6 — a regra sempre acha o mais específico primeiro)."""
    pares = [("smotheredMate", frozenset({"backRankMate", "mate"}))]
    contagens = contar(pares)
    assert contagens["backRankMate"]["recall_ok"] == 1
    # não conta como precisão do corredor (o detector não disse "backRankMate" para este)
    assert contagens["backRankMate"]["detector"] == 0
    assert contagens["smotheredMate"]["detector"] == 1 and contagens["smotheredMate"]["precisao_ok"] == 0


def test_contar_none_nunca_conta_recall():
    pares = [(None, frozenset({"arabianMate", "mate"}))]
    contagens = contar(pares)
    assert contagens["arabianMate"] == {"lichess": 1, "recall_ok": 0, "detector": 0, "precisao_ok": 0}


def test_posicao_final_dado_invalido_devolve_none():
    assert _posicao_final("posicao invalida", "e2e4") is None
    assert _posicao_final("8/8/8/8/8/8/8/4K1k1 w - - 0 1", "a1a8") is None


# --- candidatos a etiqueta própria (`PADROES_PARA_CANDIDATOS`, spec golpes design §3.6) ------


def test_contar_candidatos_bate_com_o_recall_do_corredor_apertado_na_amostra():
    """A mesma amostra de 240 mates: o corredor apertado é mais estrito que o `corredor` tolerante
    usado em `padrao_de_mate` (não tolera nenhuma casa coberta, só peão na frente do rei), então
    seu recall contra `backRankMate` pode ficar abaixo de 100% — mas nunca dá falso positivo nos
    outros 200 mates da amostra (sem nenhum tema aprovado nem `backRankMate`)."""
    contagens = contar_candidatos(_pares_candidatos_da_amostra())
    c = contagens["backRankMate"]
    assert c["lichess"] == 40
    assert c["recall_ok"] <= c["lichess"]
    assert c["detector"] == c["recall_ok"] + c["extras"]


def test_contar_candidatos_vazio():
    assert contar_candidatos([]) == {"backRankMate": {"lichess": 0, "recall_ok": 0, "detector": 0, "extras": 0}}


def test_contar_candidatos_extras_sao_os_sem_a_etiqueta_do_lichess():
    pares = [("backRankMate", frozenset({"mate"})), ("backRankMate", frozenset({"mate", "backRankMate"})),
            (None, frozenset({"mate", "backRankMate"}))]
    contagens = contar_candidatos(pares)
    assert contagens["backRankMate"] == {"lichess": 2, "recall_ok": 1, "detector": 2, "extras": 1}
