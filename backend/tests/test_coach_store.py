import pytest

from chess_trainer.coach.retrieval.chunks import Trecho
from chess_trainer.coach.retrieval.store import VectorStore
from chess_trainer.core.db import make_engine, init_db, make_session_factory
from chess_trainer.core.models import Study, StudyChapter


def trecho(key: str, chapter_id: str, texto: str, h: str = "h") -> Trecho:
    return Trecho(key=key, chapter_id=chapter_id, node_id=None, kind="intro", text=texto, comment=texto,
                  fen="", path_san="1.e4", ply=1, content_hash=h)


@pytest.fixture(params=["sqlite-vec", "numpy"])
def ambiente(request):
    engine = make_engine(":memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        db.add(Study(id="s1", title="E"))
        db.add_all([StudyChapter(id="c1", study_id="s1", order=1, name="A"), StudyChapter(id="c2", study_id="s1", order=2, name="B")])
        db.commit()
    store = VectorStore(engine, modelo="falso", dim=3, forcar_numpy=(request.param == "numpy"))
    assert store.backend == request.param
    return store, factory


def test_upsert_busca_e_contagem(ambiente):
    store, factory = ambiente
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "cravada"), trecho("k2", "c1", "garfo"), trecho("k3", "c2", "final")],
                     [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        db.commit()
        assert store.count(db) == 3
        assert [k for k, _ in store.search(db, [0.9, 0.1, 0], 2)] == ["k1", "k2"]
        assert store.hashes_do_capitulo(db, "c1") == {"k1": "h", "k2": "h"}


def test_upsert_atualiza_e_delete_apaga_o_capitulo(ambiente):
    store, factory = ambiente
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "a"), trecho("k3", "c2", "c")], [[1, 0, 0], [0, 0, 1]])
        store.upsert(db, [trecho("k1", "c1", "a2", "h2")], [[0, 1, 0]])
        db.commit()
        assert store.count(db) == 2 and store.hashes_do_capitulo(db, "c1") == {"k1": "h2"}
        assert store.search(db, [0, 1, 0], 1)[0][0] == "k1"
        store.delete_chapter(db, "c1")
        db.commit()
        assert store.count(db) == 1 and [k for k, _ in store.search(db, [0, 1, 0], 5)] == ["k3"]


def test_vetores_de_outro_modelo_ficam_fora(ambiente):
    store, factory = ambiente
    outro = VectorStore(store.engine, modelo="outro", dim=3, forcar_numpy=(store.backend == "numpy"))
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "a")], [[1, 0, 0]])
        outro.upsert(db, [trecho("k9", "c2", "z")], [[1, 0, 0]])
        db.commit()
        assert store.count(db) == 1 and [k for k, _ in store.search(db, [1, 0, 0], 5)] == ["k1"]
        assert outro.count(db) == 1 and [k for k, _ in outro.search(db, [1, 0, 0], 5)] == ["k9"]


def test_busca_nao_e_contaminada_por_outro_modelo(ambiente):
    store, factory = ambiente
    outro = VectorStore(store.engine, modelo="outro", dim=3, forcar_numpy=(store.backend == "numpy"))
    with factory() as db:
        store.upsert(db, [trecho("fa1", "c1", "a"), trecho("fa2", "c1", "b"), trecho("fa3", "c1", "c")],
                     [[0.9, 0.1, 0], [0.85, 0.15, 0], [0, 1, 0]])
        outro.upsert(db, [trecho("o1", "c2", "x"), trecho("o2", "c2", "y"), trecho("o3", "c2", "z")],
                     [[1, 0, 0], [0.99, 0.01, 0], [0.98, 0.02, 0]])
        db.commit()
        # os 3 vetores de "outro" ficam todos mais perto da consulta que os de "falso"
        assert [k for k, _ in store.search(db, [1, 0, 0], 2)] == ["fa1", "fa2"]


def test_purgar_orfaos_apos_cascade(ambiente):
    store, factory = ambiente
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "a")], [[1, 0, 0]])
        db.commit()
        db.delete(db.get(StudyChapter, "c1"))  # FK ON DELETE CASCADE apaga coach_chunks, não a tabela virtual
        db.commit()
        store.purgar_orfaos(db)
        db.commit()
        assert store.count(db) == 0 and store.search(db, [1, 0, 0], 5) == []
