import json
import random

import pytest

from chess_trainer.config import load_settings
from chess_trainer.core.golpes.assinatura import assinar
from chess_trainer.core.golpes.rotulagem import exportar_ouro, proximo_item, rotular
from chess_trainer.core.golpes.service import linha_de_assinatura, preparar
from chess_trainer.core.models import GolpeLabel, LichessPuzzleSignature
from tests.test_golpes_service import FEN_PASTOR_START, pastor


def _oito_pastores(db):
    for i in range(8):
        db.add(pastor(f"r{i}", rating=700 + 50 * i))
    db.commit()
    preparar(db, lambda *a: None)


def test_proximo_item_traz_ancora_e_candidatos_com_tier(db_session):
    _oito_pastores(db_session)
    item = proximo_item(db_session, load_settings(db_session), rng=random.Random(1))
    assert item["anchor"]["origem"] == "lichess" and item["anchor"]["assinatura"] == "Ke8 | Q xP f7 #"
    # todos os oito pastores são o mesmo golpe: o degrau "inteira" já pega todos, então os
    # degraus mais frouxos (trecho, espelho, esqueleto) não sobram candidato algum
    assert 1 <= len(item["candidatos"]) <= 2 and all(c["tier"] == "inteira" for c in item["candidatos"])
    assert item["anchor"]["id"] not in {c["id"] for c in item["candidatos"]}
    assert item["candidatos"][0]["tactic"]["fen_start"]
    assert item["candidatos"][0]["procedencia"]["degrau"] == "inteira"


def test_rotular_grava_e_o_proximo_item_nao_repete(db_session):
    _oito_pastores(db_session)
    item = proximo_item(db_session, load_settings(db_session), rng=random.Random(1))
    ancora = item["anchor"]["id"]
    for c in item["candidatos"]:
        rotular(db_session, anchor_origem="lichess", anchor_id=ancora, candidate_id=c["id"], tier=c["tier"], label="mesmo")
    assert db_session.query(GolpeLabel).count() == len(item["candidatos"])
    de_novo = proximo_item(db_session, load_settings(db_session), rng=random.Random(1), ancora=("lichess", ancora))
    assert not ({c["id"] for c in de_novo["candidatos"]} & {c["id"] for c in item["candidatos"]})
    with pytest.raises(ValueError):
        rotular(db_session, anchor_origem="lichess", anchor_id=ancora, candidate_id="r1", tier="mesmo", label="talvez")


def test_rotular_grava_a_procedencia(db_session):
    _oito_pastores(db_session)
    linha = rotular(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="trecho2",
                    label="mesmo", n_lances=2, posicao="fim", nivel="destinos", espelhado=False)
    assert linha.n_lances == 2 and linha.posicao == "fim" and linha.nivel == "destinos" and linha.espelhado is False


def test_resumo_agrega_por_procedencia(db_session):
    from chess_trainer.core.golpes.rotulagem import resumo
    _oito_pastores(db_session)
    rotular(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="inteira", label="mesmo",
           n_lances=1, posicao="inteira", nivel="destinos", espelhado=False)
    rotular(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r2", tier="inteira", label="parecido",
           n_lances=1, posicao="inteira", nivel="destinos", espelhado=False)
    rotular(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r3", tier="trecho2", label="nada",
           n_lances=2, posicao="fim", nivel="destinos", espelhado=False)
    linhas = resumo(db_session)
    por_tier = {l["tier"]: l for l in linhas}
    assert por_tier["inteira"]["mesmo"] == 1 and por_tier["inteira"]["parecido"] == 1 and por_tier["inteira"]["total"] == 2
    assert por_tier["trecho2"]["nada"] == 1 and por_tier["trecho2"]["total"] == 1
    # ordenado por tier e depois por posição
    assert [l["tier"] for l in linhas] == sorted(l["tier"] for l in linhas)


def test_exportar_ouro_uma_linha_por_rotulo(db_session):
    _oito_pastores(db_session)
    rotular(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="mesmo", label="parecido")
    linhas = [json.loads(l) for l in exportar_ouro(db_session).splitlines()]
    assert len(linhas) == 1
    assert linhas[0]["anchor_id"] == "r0" and linhas[0]["candidate_id"] == "r1" and linhas[0]["label"] == "parecido"
    assert linhas[0]["anchor_assinatura"] == linhas[0]["candidate_assinatura"] == "Ke8 | Q xP f7 #" and linhas[0]["versao"] == 2
    # procedência ausente neste rótulo (chamada sem os campos novos): fica nula, não quebra
    assert linhas[0]["n_lances"] is None and linhas[0]["posicao"] is None and linhas[0]["nivel"] is None


def test_proximo_item_traz_candidatos_de_cada_camada(db_session):
    """Três mesmos, um espelho e um esqueleto (assinaturas gravadas à mão, como em
    `test_irmaos_em_cascata_com_faixa_e_exclusao`): a cascata de `irmaos` pararia em "mesmo"
    (já dá os 3 pedidos); a rotulagem precisa ver as três camadas para formar o ouro."""
    db_session.add(pastor("anchor", rating=800))
    for i in range(3):
        db_session.add(pastor(f"m{i}", rating=700 + 50 * i))
    db_session.add(pastor("esp", rating=900))
    db_session.add(pastor("esq", rating=1000))
    db_session.commit()

    a = assinar(FEN_PASTOR_START, ["h5f7"])
    for pid in ("m0", "m1", "m2"):
        db_session.add(linha_de_assinatura(a, LichessPuzzleSignature, pid))
    db_session.add(linha_de_assinatura(a.espelhada(), LichessPuzzleSignature, "esp"))
    esq = linha_de_assinatura(a, LichessPuzzleSignature, "esq")
    esq.destinos, esq.destinos_esp = 12345, 54321  # mesmo esqueleto e zona, outras casas
    db_session.add(esq)
    db_session.commit()

    item = proximo_item(db_session, load_settings(db_session), ancora=("lichess", "anchor"), por_camada=3)
    tiers = {c["tier"] for c in item["candidatos"]}
    assert tiers == {"inteira", "espelho", "esqueleto"}
    assert {c["id"] for c in item["candidatos"] if c["tier"] == "inteira"} == {"m0", "m1", "m2"}
    assert {c["id"] for c in item["candidatos"] if c["tier"] == "espelho"} == {"esp"}
    assert {c["id"] for c in item["candidatos"] if c["tier"] == "esqueleto"} == {"esq"}


def test_proximo_item_sorteia_sem_carregar_a_tabela_toda(db_session):
    """O sorteio da âncora é um cursor no índice (`puzzle_id >= sorteio`), não uma lista de
    todos os ids — não dá para espiar o SQL aqui, mas para qualquer semente a âncora sorteada
    existe e vem com candidato (o comportamento que a implementação por cursor tem de manter)."""
    _oito_pastores(db_session)
    for seed in range(10):
        item = proximo_item(db_session, load_settings(db_session), rng=random.Random(seed))
        assert item is not None
        assert item["anchor"]["origem"] == "lichess" and item["anchor"]["id"].startswith("r")
        assert item["candidatos"]
