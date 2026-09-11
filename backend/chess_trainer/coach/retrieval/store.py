"""Armazenamento e busca dos vetores dos trechos (spec §6.3).

Os vetores ficam sempre em `coach_chunks.embedding` (float32). Com a extensão
`sqlite-vec` carregada, uma tabela virtual `coach_chunks_vec` serve a busca
KNN; sem ela, a busca é cosseno por força bruta em numpy sobre os vetores da
tabela (alguns milhares de trechos: instantâneo). A interface é a mesma."""
from __future__ import annotations

import threading

import numpy as np
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from chess_trainer.coach.retrieval.chunks import Trecho
from chess_trainer.core.db import vec_disponivel
from chess_trainer.core.models import CoachChunk, utcnow


def _normalizar(v) -> np.ndarray:
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return a / n if n else a


def _blob(v) -> bytes:
    return _normalizar(v).tobytes()


class VectorStore:
    def __init__(self, engine: Engine, modelo: str, dim: int, forcar_numpy: bool = False):
        self.engine = engine
        self.modelo = modelo
        self.dim = dim
        self.backend = "numpy" if forcar_numpy or not vec_disponivel(engine) else "sqlite-vec"
        self._lock = threading.Lock()
        self._cache: tuple[np.ndarray, list[str]] | None = None
        if self.backend == "sqlite-vec":
            self._garantir_tabela_vec()

    # --- tabela virtual -------------------------------------------------

    def _garantir_tabela_vec(self) -> None:
        """A tabela virtual tem a dimensão fixa; se mudou (modelo novo), recria."""
        with self.engine.begin() as conn:
            existe = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name = 'coach_chunks_vec'").scalar()
            if existe and f"FLOAT[{self.dim}]" not in existe:
                conn.exec_driver_sql("DROP TABLE coach_chunks_vec")
                existe = None
            if not existe:
                conn.exec_driver_sql(
                    f"CREATE VIRTUAL TABLE coach_chunks_vec USING vec0(id INTEGER PRIMARY KEY, embedding FLOAT[{self.dim}])")

    def _vec_delete(self, db: Session, ids: list[int]) -> None:
        for i in ids:
            db.execute(text("DELETE FROM coach_chunks_vec WHERE id = :id"), {"id": i})

    def _vec_insert(self, db: Session, id_: int, vetor) -> None:
        db.execute(text("INSERT INTO coach_chunks_vec(id, embedding) VALUES (:id, :emb)"), {"id": id_, "emb": _blob(vetor)})

    # --- escrita ----------------------------------------------------------

    def upsert(self, db: Session, trechos: list[Trecho], vetores: list[list[float]]) -> None:
        assert len(trechos) == len(vetores)
        for t, v in zip(trechos, vetores):
            row = db.scalar(select(CoachChunk).where(CoachChunk.key == t.key))
            if row is None:
                row = CoachChunk(key=t.key)
                db.add(row)
            row.chapter_id, row.node_id, row.kind = t.chapter_id, t.node_id, t.kind
            row.text, row.comment, row.fen, row.path_san, row.ply = t.text, t.comment, t.fen, t.path_san, t.ply
            row.content_hash, row.model, row.dim = t.content_hash, self.modelo, self.dim
            row.embedding, row.embedded_at = _blob(v), utcnow()
            db.flush()
            if self.backend == "sqlite-vec":
                self._vec_delete(db, [row.id])
                self._vec_insert(db, row.id, v)
        self._cache = None

    def delete_chapter(self, db: Session, chapter_id: str) -> None:
        ids = list(db.scalars(select(CoachChunk.id).where(CoachChunk.chapter_id == chapter_id)))
        if self.backend == "sqlite-vec":
            self._vec_delete(db, ids)
        db.execute(delete(CoachChunk).where(CoachChunk.chapter_id == chapter_id))
        self._cache = None

    def purgar_orfaos(self, db: Session) -> None:
        """Linhas da tabela virtual cujo trecho sumiu (o CASCADE do capítulo não a alcança)."""
        if self.backend == "sqlite-vec":
            db.execute(text("DELETE FROM coach_chunks_vec WHERE id NOT IN (SELECT id FROM coach_chunks)"))
        self._cache = None

    # --- leitura ----------------------------------------------------------

    def count(self, db: Session) -> int:
        return len(list(db.scalars(select(CoachChunk.id).where(CoachChunk.model == self.modelo))))

    def hashes_do_capitulo(self, db: Session, chapter_id: str) -> dict[str, str]:
        rows = db.execute(select(CoachChunk.key, CoachChunk.content_hash)
                          .where(CoachChunk.chapter_id == chapter_id, CoachChunk.model == self.modelo)).all()
        return {k: h for k, h in rows}

    def search(self, db: Session, vetor: list[float], k: int) -> list[tuple[str, float]]:
        if k <= 0:
            return []
        if self.backend == "sqlite-vec":
            # os vetores são unitários: a distância L2 ordena igual ao cosseno
            hits = db.execute(text("SELECT id, distance FROM coach_chunks_vec WHERE embedding MATCH :q AND k = :k ORDER BY distance"),
                              {"q": _blob(vetor), "k": k}).all()
            if not hits:
                return []
            por_id = {i: d for i, d in hits}
            rows = db.execute(select(CoachChunk.id, CoachChunk.key)
                              .where(CoachChunk.id.in_(list(por_id)), CoachChunk.model == self.modelo)).all()
            return sorted(((key, float(por_id[i])) for i, key in rows), key=lambda x: x[1])
        matriz, chaves = self._matriz(db)
        if not chaves:
            return []
        sims = matriz @ _normalizar(vetor)
        ordem = np.argsort(-sims)[:k]
        return [(chaves[i], float(1.0 - sims[i])) for i in ordem]

    def _matriz(self, db: Session) -> tuple[np.ndarray, list[str]]:
        with self._lock:
            if self._cache is None:
                rows = db.execute(select(CoachChunk.key, CoachChunk.embedding).where(CoachChunk.model == self.modelo)).all()
                chaves = [k for k, _ in rows]
                matriz = (np.stack([np.frombuffer(e, dtype=np.float32) for _, e in rows])
                          if rows else np.zeros((0, self.dim), dtype=np.float32))
                self._cache = (matriz, chaves)
            return self._cache
