import json
from datetime import datetime, timedelta

import chess
import pytest

from chess_trainer.coach.retrieval.index import Indexador
from chess_trainer.config import get_setting
from chess_trainer.core.db import init_db, make_engine, make_session_factory
from chess_trainer.core.models import Study, StudyChapter, utcnow
from tests.fakes import EmbeddingsFalso


def arvore(comentario: str):
    return {"fen": chess.STARTING_FEN, "orientation": "white", "intro": "",
            "root": {"children": [{"id": "n1", "uci": "e2e4", "san": "e4", "comment": comentario, "children": []}]}}


@pytest.fixture
def ambiente():
    engine = make_engine(":memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    emb = EmbeddingsFalso()
    idx = Indexador(engine, emb)
    with factory() as db:
        s = Study(id="s1", title="Táticas básicas")
        db.add(s)
        db.add(StudyChapter(id="c1", study_id="s1", order=1, name="Cravadas", updated_at=datetime(2026, 1, 1),
                            tree_json=json.dumps(arvore("A cravada absoluta prende a peça ao rei e decide a partida."))))
        db.add(StudyChapter(id="c2", study_id="s1", order=2, name="Garfos", updated_at=datetime(2026, 1, 1),
                            tree_json=json.dumps(arvore("O garfo de cavalo ataca duas peças ao mesmo tempo sem defesa."))))
        db.commit()
    return idx, factory, emb


def test_sem_modelo_pronto_nao_indexa_e_status_avisa(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        assert idx.modelo_pronto(db) is False
        assert idx.indexar_capitulo(db, db.get(StudyChapter, "c1")) == 0
        st = idx.status(db)
        assert st["embeddings_ready"] is False and st["index_chunks"] == 0 and st["index_stale"] == 2
        assert idx.buscar(db, "cravada", 3) == []


def test_recriar_baixa_o_modelo_indexa_tudo_e_busca(ambiente):
    idx, factory, emb = ambiente
    progresso = []
    with factory() as db:
        n = idx.recriar(db, lambda *a: progresso.append(a))
        db.commit()
        assert emb.preparado and n == 2 and get_setting(db, "coach_embeddings_ready") == "falso"
        assert progresso[-1][:3] == ("coach_reindex", 2, 2)
        st = idx.status(db)
        assert st["index_chunks"] == 2 and st["index_stale"] == 0 and st["index_model"] == "falso"
        hits = idx.buscar(db, "cravada absoluta rei", 1)
        assert len(hits) == 1 and hits[0]["chapter_id"] == "c1" and hits[0]["capitulo"] == "Cravadas"
        assert hits[0]["url"] == "/estudos/s1/capitulos/c1?lance=n1" and hits[0]["caminho_san"] == "1.e4"
        assert hits[0]["texto"].startswith("A cravada absoluta") and len(hits[0]["chunk_id"]) == 10


def test_indexar_capitulo_pula_trechos_iguais_e_remove_os_que_sumiram(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        db.commit()
        chamadas_antes = len(emb.chamadas)
        c1 = db.get(StudyChapter, "c1")
        assert idx.indexar_capitulo(db, c1) == 1 and len(emb.chamadas) == chamadas_antes  # nada mudou: sem embed
        c1.tree_json = json.dumps(arvore(""))  # comentário apagado
        c1.updated_at = datetime(2026, 2, 1)
        db.flush()
        assert idx.indexar_capitulo(db, c1) == 0
        db.commit()
        assert idx.status(db)["index_chunks"] == 1 and idx.status(db)["index_stale"] == 0


def test_capitulo_editado_depois_do_indice_conta_como_desatualizado(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        c2 = db.get(StudyChapter, "c2")
        c2.updated_at = utcnow() + timedelta(minutes=5)
        db.commit()
        assert idx.status(db)["index_stale"] == 1
        idx.remover_capitulo(db, "c2")
        db.commit()
        assert idx.status(db)["index_chunks"] == 1


def test_busca_traz_tambem_a_mesma_abertura(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        db.commit()
        hits = idx.buscar(db, "garfo cavalo", 1, caminho_san="1.e4 e5 2.Nf3 Nc6 3.Bb5 a6")
        # k=1 pela busca vetorial (garfos) + o trecho com o mesmo começo de partida (1.e4), sem duplicar
        assert [h["chapter_id"] for h in hits] == ["c2", "c1"]


def test_troca_de_modelo_invalida_o_indice(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        db.commit()
        outro = Indexador(idx.store.engine, EmbeddingsFalso(modelo="falso-v2"))
        assert outro.modelo_pronto(db) is False and outro.status(db)["index_chunks"] == 0
        assert idx.modelo_pronto(db) is True  # o índice do modelo antigo continua íntegro
