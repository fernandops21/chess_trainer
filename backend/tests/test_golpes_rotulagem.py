import json
import random

import pytest

from chess_trainer.config import load_settings
from chess_trainer.core.golpes.rotulagem import exportar_ouro, proximo_item, rotular
from chess_trainer.core.golpes.service import preparar
from chess_trainer.core.models import GolpeLabel
from tests.test_golpes_service import pastor


def _oito_pastores(db):
    for i in range(8):
        db.add(pastor(f"r{i}", rating=700 + 50 * i))
    db.commit()
    preparar(db, lambda *a: None)


def test_proximo_item_traz_ancora_e_candidatos_com_tier(db_session):
    _oito_pastores(db_session)
    item = proximo_item(db_session, load_settings(db_session), rng=random.Random(1))
    assert item["anchor"]["origem"] == "lichess" and item["anchor"]["assinatura"] == "Ke8 | Q xP f7 #"
    assert 1 <= len(item["candidatos"]) <= 3 and all(c["tier"] == "mesmo" for c in item["candidatos"])
    assert item["anchor"]["id"] not in {c["id"] for c in item["candidatos"]}
    assert item["candidatos"][0]["tactic"]["fen_start"]


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


def test_exportar_ouro_uma_linha_por_rotulo(db_session):
    _oito_pastores(db_session)
    rotular(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="mesmo", label="parecido")
    linhas = [json.loads(l) for l in exportar_ouro(db_session).splitlines()]
    assert len(linhas) == 1
    assert linhas[0]["anchor_id"] == "r0" and linhas[0]["candidate_id"] == "r1" and linhas[0]["label"] == "parecido"
    assert linhas[0]["anchor_assinatura"] == linhas[0]["candidate_assinatura"] == "Ke8 | Q xP f7 #" and linhas[0]["versao"] == 1
