"""Índice dos trechos dos estudos: indexar capítulo a capítulo, recriar tudo,
estado e busca (spec §6.4). Precisa do modelo de embeddings já baixado
(`coach_embeddings_ready`); sem ele, os capítulos ficam marcados como
desatualizados e a busca devolve vazio."""
from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from chess_trainer.api.jobs import ProgressFn
from chess_trainer.coach.retrieval.chunks import trechos_do_capitulo
from chess_trainer.coach.retrieval.embeddings import Embeddings
from chess_trainer.coach.retrieval.store import VectorStore
from chess_trainer.config import get_setting, set_setting
from chess_trainer.core.models import CoachChunk, CoachIndexedChapter, Study, StudyChapter, utcnow
from chess_trainer.core.studies.tree import chapter_tree

CHAVE_MODELO_PRONTO = "coach_embeddings_ready"
PLIES_MESMA_ABERTURA = 6
EXTRA_MESMA_ABERTURA = 3

log = logging.getLogger(__name__)


class Indexador:
    def __init__(self, engine: Engine, embeddings: Embeddings, forcar_numpy: bool = False):
        self.embeddings = embeddings
        self.store = VectorStore(engine, embeddings.modelo, embeddings.dim, forcar_numpy=forcar_numpy)

    def modelo_pronto(self, db: Session) -> bool:
        return get_setting(db, CHAVE_MODELO_PRONTO) == self.embeddings.modelo

    # --- escrita ----------------------------------------------------------

    def indexar_capitulo(self, db: Session, chapter: StudyChapter) -> int:
        """Reindexa um capítulo; só embute os trechos novos ou alterados. Devolve quantos trechos ele tem no índice.

        Nunca levanta: o índice é acessório e roda pendurado no salvamento do
        capítulo. Se der errado (o modelo sumiu do disco, por exemplo), devolve 0
        sem gravar a marca — o capítulo fica contando como desatualizado e o
        "Recriar índice" o arruma."""
        if not self.modelo_pronto(db):
            return 0
        try:
            estudo = chapter.study.title if chapter.study is not None else ""
            trechos = trechos_do_capitulo(chapter.id, estudo, chapter.name, chapter_tree(chapter))
            existentes = self.store.hashes_do_capitulo(db, chapter.id)
            novos = [t for t in trechos if existentes.get(t.key) != t.content_hash]
            # algum trecho sumiu: recomeça o capítulo (poucas dezenas de linhas)
            recomecar = bool(set(existentes) - {t.key for t in trechos})
            if recomecar:
                novos = trechos
            # embute antes de apagar: uma falha aqui não deixa o capítulo sem os vetores antigos
            vetores = self.embeddings.embed([t.text for t in novos]) if novos else []
            if recomecar:
                self.store.delete_chapter(db, chapter.id)
            if novos:
                self.store.upsert(db, novos, vetores)
        except Exception:
            log.warning("não deu para indexar o capítulo %s; ele fica desatualizado", chapter.id, exc_info=True)
            return 0
        marca = db.get(CoachIndexedChapter, chapter.id)
        if marca is None:
            marca = CoachIndexedChapter(chapter_id=chapter.id)
            db.add(marca)
        marca.indexed_at, marca.n_chunks, marca.model = utcnow(), len(trechos), self.embeddings.modelo
        db.flush()
        return len(trechos)

    def remover_capitulo(self, db: Session, chapter_id: str) -> None:
        self.store.delete_chapter(db, chapter_id)
        marca = db.get(CoachIndexedChapter, chapter_id)
        if marca is not None:
            db.delete(marca)
        db.flush()

    def remover_estudo(self, db: Session, study: Study) -> None:
        """Tira do índice todos os capítulos do estudo. O CASCADE do banco apaga
        `coach_chunks`, mas não a tabela virtual dos vetores nem o cache da busca."""
        for chapter in list(study.chapters):
            self.remover_capitulo(db, chapter.id)

    def indexar_estudo(self, db: Session, study: Study) -> int:
        """Como `indexar_capitulo`, nunca levanta: também roda pendurada na importação."""
        total = 0
        try:
            for chapter in study.chapters:
                total += self.indexar_capitulo(db, chapter)
            # capítulos que a reimportação derrubou deixam vetores órfãos na tabela virtual
            self.store.purgar_orfaos(db)
        except Exception:
            log.warning("não deu para indexar o estudo %s", study.id, exc_info=True)
        return total

    def recriar(self, db: Session, progress: ProgressFn, should_stop: Callable[[], bool] | None = None) -> int:
        """Baixa o modelo se preciso, apaga o índice e reindexa todos os capítulos.

        `should_stop` é consultado antes de cada capítulo: pedida a parada, o que já
        foi indexado é commitado e os capítulos restantes ficam desatualizados (o
        "Recriar índice" seguinte os arruma). Devolve quantos capítulos foram feitos."""
        progress("coach_reindex", 0, 0, "preparando o modelo de embeddings")
        self.embeddings.preparar()
        set_setting(db, CHAVE_MODELO_PRONTO, self.embeddings.modelo)
        capitulos = list(db.scalars(select(StudyChapter).order_by(StudyChapter.study_id, StudyChapter.order)))
        for c in capitulos:
            self.store.delete_chapter(db, c.id)
        self.store.purgar_orfaos(db)
        total = len(capitulos)
        for i, c in enumerate(capitulos, start=1):
            if should_stop is not None and should_stop():
                progress("coach_reindex", i, total, "cancelado")
                db.commit()
                return i - 1
            self.indexar_capitulo(db, c)
            progress("coach_reindex", i, total, f"{i}/{total} capítulos")
        db.commit()
        return total

    # --- leitura ----------------------------------------------------------

    def status(self, db: Session) -> dict:
        capitulos = db.execute(select(StudyChapter.id, StudyChapter.updated_at)).all()
        marcas = {m.chapter_id: m for m in db.scalars(select(CoachIndexedChapter))}
        desatualizados = 0
        for cid, updated_at in capitulos:
            m = marcas.get(cid)
            if m is None or m.model != self.embeddings.modelo or (updated_at is not None and updated_at > m.indexed_at):
                desatualizados += 1
        return {
            "embeddings_ready": self.modelo_pronto(db),
            "index_chunks": self.store.count(db),
            "index_model": self.embeddings.modelo,
            "index_stale": desatualizados,
            "vector_backend": self.store.backend,
        }

    def buscar(self, db: Session, consulta: str, k: int = 5, caminho_san: str | None = None) -> list[dict]:
        if not self.modelo_pronto(db) or not consulta.strip():
            return []
        vetor = self.embeddings.embed([consulta])[0]
        chaves = [key for key, _ in self.store.search(db, vetor, k)]
        if caminho_san:
            # "mesma abertura": o caminho do trecho é prefixo dos primeiros plies da partida
            # ou vice-versa (um comentário em 1.e4 vale para qualquer partida que começou assim)
            prefixo = " ".join(caminho_san.split()[:PLIES_MESMA_ABERTURA])
            candidatos = db.execute(select(CoachChunk.key, CoachChunk.path_san)
                                    .where(CoachChunk.model == self.embeddings.modelo, CoachChunk.path_san != "")).all()
            extras = 0
            for key, path in candidatos:
                if key in chaves or extras >= EXTRA_MESMA_ABERTURA:
                    continue
                if prefixo.startswith(path) or path.startswith(prefixo):
                    chaves.append(key)
                    extras += 1
        if not chaves:
            return []
        rows = {r.key: r for r in db.scalars(select(CoachChunk).where(CoachChunk.key.in_(chaves)))}
        out = []
        for key in chaves:
            r = rows.get(key)
            if r is None:
                continue
            capitulo = db.get(StudyChapter, r.chapter_id)
            estudo = capitulo.study if capitulo is not None else None
            url = f"/estudos/{capitulo.study_id}/capitulos/{capitulo.id}" if capitulo is not None else ""
            if r.node_id:
                url += f"?lance={r.node_id}"
            out.append({
                "chunk_id": r.key, "study_id": capitulo.study_id if capitulo else "", "estudo": estudo.title if estudo else "",
                "chapter_id": r.chapter_id, "capitulo": capitulo.name if capitulo else "", "node_id": r.node_id,
                "caminho_san": r.path_san, "texto": r.comment, "url": url,
            })
        return out
