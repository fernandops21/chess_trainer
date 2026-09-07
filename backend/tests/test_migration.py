"""Migração de um banco do esquema anterior (sem fontes de exercício).

O banco de um usuário já em uso não pode perder nada: a migração só acrescenta
colunas e tabelas. O esquema antigo abaixo é uma cópia literal do `CREATE TABLE`
que o projeto gerava antes deste ciclo.
"""

import sqlite3
from datetime import datetime

import pytest

from chess_trainer.core.db import init_db, make_engine, make_session_factory
from chess_trainer.core.models import Puzzle, Study, StudyChapter

OLD_SCHEMA = """
CREATE TABLE games (
	id VARCHAR(36) NOT NULL,
	source VARCHAR(32) NOT NULL,
	source_id VARCHAR(255) NOT NULL,
	pgn TEXT NOT NULL,
	white VARCHAR(64) NOT NULL,
	black VARCHAR(64) NOT NULL,
	result VARCHAR(8) NOT NULL,
	time_control VARCHAR(32) NOT NULL,
	category VARCHAR(16) NOT NULL,
	played_at DATETIME NOT NULL,
	my_color VARCHAR(5) NOT NULL,
	imported_at DATETIME NOT NULL,
	analyzed_at DATETIME,
	analysis_depth INTEGER,
	PRIMARY KEY (id),
	UNIQUE (source_id)
);
CREATE TABLE positions (
	id VARCHAR(36) NOT NULL,
	game_id VARCHAR(36) NOT NULL,
	ply INTEGER NOT NULL,
	fen VARCHAR(100) NOT NULL,
	move_played VARCHAR(10) NOT NULL,
	move_uci VARCHAR(6) NOT NULL,
	eval_before INTEGER NOT NULL,
	eval_after INTEGER NOT NULL,
	best_move VARCHAR(6),
	best_eval INTEGER NOT NULL,
	is_mistake BOOLEAN NOT NULL,
	mistake_level VARCHAR(8),
	mistake_by VARCHAR(8),
	PRIMARY KEY (id),
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE TABLE puzzles (
	id VARCHAR(36) NOT NULL,
	position_id VARCHAR(36) NOT NULL,
	game_id VARCHAR(36) NOT NULL,
	kind VARCHAR(8) NOT NULL,
	fen_start VARCHAR(100) NOT NULL,
	side_to_move VARCHAR(5) NOT NULL,
	solution TEXT NOT NULL,
	end_reason VARCHAR(16) NOT NULL,
	theme VARCHAR(24) NOT NULL,
	category VARCHAR(16) NOT NULL,
	solver_moves INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	is_leech BOOLEAN NOT NULL,
	leech_since DATETIME,
	srs_ease FLOAT NOT NULL,
	srs_interval_days INTEGER NOT NULL,
	srs_lapses INTEGER NOT NULL,
	srs_due_at DATETIME,
	srs_last_reviewed_at DATETIME,
	PRIMARY KEY (id),
	CONSTRAINT uq_puzzle_fen_kind UNIQUE (fen_start, kind),
	FOREIGN KEY(position_id) REFERENCES positions (id),
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE TABLE settings (
	"key" VARCHAR(64) NOT NULL,
	value TEXT NOT NULL,
	PRIMARY KEY ("key")
);
CREATE TABLE reviews (
	id VARCHAR(36) NOT NULL,
	puzzle_id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36),
	reviewed_at DATETIME NOT NULL,
	result VARCHAR(8) NOT NULL,
	used_hint BOOLEAN NOT NULL,
	duration_ms INTEGER NOT NULL,
	ease FLOAT NOT NULL,
	interval_days INTEGER NOT NULL,
	due_at DATETIME NOT NULL,
	lapses INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(puzzle_id) REFERENCES puzzles (id)
);
"""

PUZZLE_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def old_db(tmp_path):
    """Banco em arquivo no esquema anterior, com uma partida, uma posição,
    um puzzle e uma revisão."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO games VALUES ('g1','chess.com','src-1','1. e4 e5 1-0','eu','ele','1-0','600',"
        "'rapid','2026-08-01 12:00:00','white','2026-08-02 10:00:00',NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO positions VALUES ('p1','g1',7,'fen-antes','Nf6','g8f6',20,-300,'d7d5',10,1,'blunder','opponent')"
    )
    conn.execute(
        "INSERT INTO puzzles VALUES (?,'p1','g1','punish','fen-do-puzzle','white',"
        "'{\"moves\": []}','material_gain','tactic','rapid',1,'2026-08-02 10:05:00',0,NULL,"
        "2.5,3,1,'2026-09-01 00:00:00','2026-08-29 09:00:00')",
        (PUZZLE_ID,),
    )
    conn.execute(
        "INSERT INTO reviews VALUES ('r1',?,NULL,'2026-08-29 09:00:00','correct',0,1200,2.5,3,"
        "'2026-09-01 00:00:00',1)",
        (PUZZLE_ID,),
    )
    conn.commit()
    conn.close()
    return path


def _column_names(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(puzzles)")}
    finally:
        conn.close()


def test_migracao_acrescenta_colunas_sem_perder_puzzles(old_db):
    engine = make_engine(str(old_db))
    init_db(engine)
    try:
        with make_session_factory(engine)() as db:
            puzzle = db.get(Puzzle, PUZZLE_ID)
            assert puzzle is not None
            # nada do histórico se perde
            assert puzzle.fen_start == "fen-do-puzzle"
            assert puzzle.srs_interval_days == 3 and puzzle.srs_lapses == 1
            assert puzzle.srs_due_at == datetime(2026, 9, 1)
            assert len(puzzle.reviews) == 1
            # padrões das colunas novas
            assert puzzle.source == "own"
            assert puzzle.in_queue is True
            assert puzzle.external_id is None
            assert puzzle.chapter_id is None
            assert puzzle.fen_before is None
            assert puzzle.last_move is None
    finally:
        engine.dispose()


def test_migracao_e_idempotente(old_db):
    engine = make_engine(str(old_db))
    init_db(engine)
    init_db(engine)  # segunda passada não pode falhar nem duplicar colunas
    try:
        colunas = [c for c in _column_names(old_db)]
        assert len(colunas) == len(set(colunas))
        assert {"source", "in_queue", "external_id", "chapter_id", "fen_before", "last_move"} <= set(colunas)
        with make_session_factory(engine)() as db:
            assert db.query(Puzzle).count() == 1
    finally:
        engine.dispose()


def test_migracao_cria_indices_unicos_novos(old_db):
    engine = make_engine(str(old_db))
    init_db(engine)
    try:
        conn = sqlite3.connect(old_db)
        indices = {row[1] for row in conn.execute("PRAGMA index_list(puzzles)")}
        conn.close()
        assert "uq_puzzle_fen_kind_source" in indices
        assert "uq_puzzle_external_id" in indices
    finally:
        engine.dispose()


def test_migracao_cria_tabelas_de_estudo(old_db):
    engine = make_engine(str(old_db))
    init_db(engine)
    try:
        with make_session_factory(engine)() as db:
            estudo = Study(title="Aulas do Basso", author="basso", source_url="https://lichess.org/study/4JKVAfaE",
                           lichess_id="4JKVAfaE")
            db.add(estudo)
            db.flush()
            capitulo = StudyChapter(study_id=estudo.id, order=1, name="Capítulo 1", fen="fen-cap",
                                    orientation="white", mode="gamebook", pgn="1. e4 *")
            db.add(capitulo)
            db.commit()
            db.refresh(estudo)
            assert [c.name for c in estudo.chapters] == ["Capítulo 1"]
            assert capitulo.in_queue is True and capitulo.puzzle_id is None
            assert capitulo.intro_comment == ""
    finally:
        engine.dispose()


def test_banco_novo_tambem_passa_pela_migracao(tmp_path):
    """Banco criado do zero por `create_all` já tem as colunas: migrar de novo
    não pode dar erro."""
    path = tmp_path / "novo.db"
    engine = make_engine(str(path))
    init_db(engine)
    init_db(engine)
    try:
        assert {"source", "in_queue"} <= _column_names(path)
    finally:
        engine.dispose()
