import json

import pytest

from chess_trainer.core.golpes.votos import exportar_ouro, resumo, voto_de, votar
from chess_trainer.core.models import GolpeLabel
from tests.test_golpes_service import pastor


def _dois_pastores(db):
    db.add(pastor("r0", rating=700))
    db.add(pastor("r1", rating=750))
    db.commit()


def test_votar_grava_uma_linha_com_a_procedencia(db_session):
    _dois_pastores(db_session)
    linha = votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="trecho2",
                 label="mesmo", n_lances=2, posicao="fim", nivel="destinos", espelhado=False)
    assert db_session.query(GolpeLabel).count() == 1
    assert linha.n_lances == 2 and linha.posicao == "fim" and linha.nivel == "destinos" and linha.espelhado is False
    assert linha.label == "mesmo" and linha.tier_na_hora == "trecho2"


def test_votar_de_novo_no_mesmo_par_atualiza_em_vez_de_duplicar(db_session):
    _dois_pastores(db_session)
    primeiro = votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="inteira", label="nada")
    segundo = votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="inteira", label="mesmo",
                    n_lances=1, posicao="inteira", nivel="destinos", espelhado=False)
    assert db_session.query(GolpeLabel).count() == 1
    assert segundo.id == primeiro.id
    assert db_session.get(GolpeLabel, primeiro.id).label == "mesmo"


def test_votar_rotulo_invalido(db_session):
    _dois_pastores(db_session)
    with pytest.raises(ValueError):
        votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="inteira", label="talvez")


def test_voto_de_devolve_o_rotulo_gravado_ou_nulo(db_session):
    _dois_pastores(db_session)
    assert voto_de(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1") is None
    votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="inteira", label="parecido")
    assert voto_de(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1") == "parecido"


def test_resumo_agrega_por_procedencia(db_session):
    _dois_pastores(db_session)
    db_session.add(pastor("r2", rating=800))
    db_session.add(pastor("r3", rating=850))
    db_session.commit()
    votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="inteira", label="mesmo",
         n_lances=1, posicao="inteira", nivel="destinos", espelhado=False)
    votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r2", tier="inteira", label="parecido",
         n_lances=1, posicao="inteira", nivel="destinos", espelhado=False)
    votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r3", tier="trecho2", label="nada",
         n_lances=2, posicao="fim", nivel="destinos", espelhado=False)
    linhas = resumo(db_session)
    por_tier = {l["tier"]: l for l in linhas}
    assert por_tier["inteira"]["mesmo"] == 1 and por_tier["inteira"]["parecido"] == 1 and por_tier["inteira"]["total"] == 2
    assert por_tier["trecho2"]["nada"] == 1 and por_tier["trecho2"]["total"] == 1
    # ordenado por tier e depois por posição
    assert [l["tier"] for l in linhas] == sorted(l["tier"] for l in linhas)


def test_exportar_ouro_uma_linha_por_par(db_session):
    _dois_pastores(db_session)
    votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="mesmo", label="parecido")
    # votar de novo no mesmo par não pode gerar uma segunda linha no export
    votar(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="mesmo", label="mesmo")
    linhas = [json.loads(l) for l in exportar_ouro(db_session).splitlines()]
    assert len(linhas) == 1
    assert linhas[0]["anchor_id"] == "r0" and linhas[0]["candidate_id"] == "r1" and linhas[0]["label"] == "mesmo"
    assert linhas[0]["anchor_assinatura"] == linhas[0]["candidate_assinatura"] == "Ke8 | Q xP f7 #" and linhas[0]["versao"] == 2
    # procedência ausente neste voto (chamada sem os campos novos): fica nula, não quebra
    assert linhas[0]["n_lances"] is None and linhas[0]["posicao"] is None and linhas[0]["nivel"] is None
