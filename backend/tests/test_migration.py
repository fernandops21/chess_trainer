"""Migração de um banco do esquema anterior (sem fontes de exercício).

O banco de um usuário já em uso não pode perder nada: a migração só acrescenta
colunas e tabelas. O esquema antigo abaixo é uma cópia literal do `CREATE TABLE`
que o projeto gerava antes deste ciclo.
"""

import sqlite3
from datetime import datetime

import pytest

from chess_trainer.core.db import init_db, make_engine, make_session_factory
from chess_trainer.core.models import CoachExplanation, Puzzle, Review, Study, StudyChapter

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


def _notnull(path, coluna: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return next(row[3] for row in conn.execute("PRAGMA table_info(puzzles)") if row[1] == coluna)
    finally:
        conn.close()


def _ddl_puzzles(path) -> str:
    """DDL de `puzzles` guardada no banco. O `ALTER TABLE ... RENAME TO` do
    SQLite grava o nome novo entre aspas: só isso é normalizado."""
    conn = sqlite3.connect(path)
    try:
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='puzzles'").fetchone()[0]
        return ddl.replace('CREATE TABLE "puzzles"', "CREATE TABLE puzzles", 1)
    finally:
        conn.close()


def _backups(path) -> list:
    return sorted(path.parent.glob(f"{path.name}.bak-*"))


def _puzzle_de_fonte(**over) -> Puzzle:
    base = dict(source="lichess", position_id=None, game_id=None, kind="punish", fen_start="fen-lichess",
                side_to_move="white", solution="{}", end_reason="mate", theme="fork", category="lichess",
                solver_moves=1)
    base.update(over)
    return Puzzle(**base)


def test_migracao_aceita_puzzle_sem_partida_nem_posicao(old_db):
    """O esquema antigo tinha `position_id`/`game_id` NOT NULL; sem a
    reconstrução da tabela, um puzzle do Lichess não entra no banco migrado."""
    engine = make_engine(str(old_db))
    init_db(engine)
    try:
        assert _notnull(old_db, "position_id") == 0 and _notnull(old_db, "game_id") == 0
        with make_session_factory(engine)() as db:
            puzzle = _puzzle_de_fonte(external_id="abc")
            db.add(puzzle)
            db.commit()
            gravado = db.get(Puzzle, puzzle.id)
            assert gravado.position_id is None and gravado.game_id is None
            assert gravado.source == "lichess" and gravado.in_queue is True
    finally:
        engine.dispose()


def test_migracao_solta_a_restricao_antiga_de_fen_e_kind(old_db):
    """A `UNIQUE(fen_start, kind)` do esquema antigo dava lugar à
    `UNIQUE(fen_start, kind, source)`: mesma posição em fontes diferentes convive."""
    engine = make_engine(str(old_db))
    init_db(engine)
    try:
        with make_session_factory(engine)() as db:
            db.add(_puzzle_de_fonte(fen_start="fen-do-puzzle", kind="punish", external_id="00sHx"))
            db.commit()
            assert db.query(Puzzle).filter_by(fen_start="fen-do-puzzle").count() == 2
    finally:
        engine.dispose()


def test_migracao_preserva_puzzle_revisao_e_vinculo(old_db):
    engine = make_engine(str(old_db))
    init_db(engine)
    try:
        with make_session_factory(engine)() as db:
            puzzle = db.get(Puzzle, PUZZLE_ID)
            assert puzzle.fen_start == "fen-do-puzzle" and puzzle.position_id == "p1" and puzzle.game_id == "g1"
            assert puzzle.srs_ease == 2.5 and puzzle.srs_interval_days == 3 and puzzle.srs_lapses == 1
            assert puzzle.srs_due_at == datetime(2026, 9, 1)
            revisao = db.get(Review, "r1")
            assert revisao is not None and revisao.puzzle is puzzle
            assert [r.id for r in puzzle.reviews] == ["r1"]
            # a FK reviews → puzzles continua valendo depois da reconstrução
            db.add(Review(id="r2", puzzle_id=PUZZLE_ID, result="correct", used_hint=False, duration_ms=900,
                          reviewed_at=datetime(2026, 9, 2), ease=2.6, interval_days=6,
                          due_at=datetime(2026, 9, 8), lapses=1))
            db.commit()
            assert db.query(Review).count() == 2
    finally:
        engine.dispose()


def test_migracao_deixa_o_esquema_igual_ao_de_um_banco_novo(old_db, tmp_path):
    engine = make_engine(str(old_db))
    init_db(engine)
    novo = tmp_path / "novo.db"
    engine_novo = make_engine(str(novo))
    init_db(engine_novo)
    try:
        assert _ddl_puzzles(old_db) == _ddl_puzzles(novo)
    finally:
        engine.dispose()
        engine_novo.dispose()


def test_migracao_copia_o_banco_antes_de_reconstruir_uma_vez_so(old_db):
    engine = make_engine(str(old_db))
    init_db(engine)
    try:
        copias = _backups(old_db)
        assert len(copias) == 1
        # a cópia é do esquema anterior: tem o puzzle e ainda o NOT NULL
        assert _notnull(copias[0], "position_id") == 1
        conn = sqlite3.connect(copias[0])
        assert conn.execute("SELECT count(*) FROM puzzles").fetchone()[0] == 1
        # e sai antes de qualquer ALTER: ainda sem as colunas novas
        colunas = {row[1] for row in conn.execute("PRAGMA table_info(puzzles)")}
        assert "source" not in colunas and "in_queue" not in colunas
        conn.close()
        # segunda passada não reconstrói nem copia de novo
        copias[0].unlink()
        init_db(engine)
        assert _backups(old_db) == []
    finally:
        engine.dispose()


def test_banco_novo_nao_e_reconstruido_nem_copiado(tmp_path):
    path = tmp_path / "novo.db"
    engine = make_engine(str(path))
    init_db(engine)
    init_db(engine)
    try:
        assert _backups(path) == []
    finally:
        engine.dispose()


# --- colunas do editor de estudos ----------------------------------------

# colunas que o ciclo do editor acrescentou; o banco do usuário vem sem elas
COLUNAS_NOVAS = {"studies": ("origin", "updated_at"), "study_chapters": ("tree_json", "updated_at")}


@pytest.fixture
def db_do_ciclo_anterior(tmp_path):
    """Banco no esquema do ciclo dos estudos importados: igual ao de hoje, sem
    as colunas do editor (o `DROP COLUMN` do SQLite as tira do banco novo)."""
    path = tmp_path / "estudos.db"
    engine = make_engine(str(path))
    init_db(engine)
    with make_session_factory(engine)() as db:
        estudo = Study(id="e1", title="Aulas do Basso", author="basso01",
                       source_url="https://lichess.org/study/4JKVAfaE", lichess_id="4JKVAfaE")
        db.add(estudo)
        db.flush()
        db.add(StudyChapter(id="c1", study_id="e1", order=1, name="Capítulo 1", fen="fen-cap",
                            orientation="white", mode="gamebook", pgn="1. e4 *", intro_comment="Enunciado"))
        db.commit()
    engine.dispose()
    conn = sqlite3.connect(path)
    for tabela, colunas in COLUNAS_NOVAS.items():
        for coluna in colunas:
            conn.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")
    conn.commit()
    conn.close()
    return path


def _colunas(path, tabela: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}
    finally:
        conn.close()


def test_migracao_acrescenta_as_colunas_do_editor(db_do_ciclo_anterior):
    assert "origin" not in _colunas(db_do_ciclo_anterior, "studies")
    engine = make_engine(str(db_do_ciclo_anterior))
    init_db(engine)
    try:
        assert {"origin", "updated_at"} <= _colunas(db_do_ciclo_anterior, "studies")
        assert {"tree_json", "updated_at"} <= _colunas(db_do_ciclo_anterior, "study_chapters")
        with make_session_factory(engine)() as db:
            estudo = db.get(Study, "e1")
            # o estudo que já existia veio do Lichess
            assert estudo is not None and estudo.origin == "lichess"
            assert estudo.title == "Aulas do Basso" and estudo.lichess_id == "4JKVAfaE"
            capitulo = db.get(StudyChapter, "c1")
            assert capitulo.name == "Capítulo 1" and capitulo.pgn == "1. e4 *"
            assert capitulo.intro_comment == "Enunciado"
            # sem árvore ainda: o editor a monta na primeira abertura
            assert not capitulo.tree_json
    finally:
        engine.dispose()


def test_migracao_das_colunas_do_editor_e_idempotente(db_do_ciclo_anterior):
    engine = make_engine(str(db_do_ciclo_anterior))
    init_db(engine)
    init_db(engine)
    try:
        for tabela, colunas in COLUNAS_NOVAS.items():
            nomes = [row[1] for row in sqlite3.connect(db_do_ciclo_anterior).execute(f"PRAGMA table_info({tabela})")]
            assert len(nomes) == len(set(nomes))
            assert set(colunas) <= set(nomes)
        with make_session_factory(engine)() as db:
            assert db.query(Study).count() == 1 and db.query(StudyChapter).count() == 1
    finally:
        engine.dispose()


def test_migracao_grava_a_arvore_do_capitulo_antigo_na_primeira_leitura(db_do_ciclo_anterior):
    """Capítulo importado antes do editor: `ensure_tree` monta a árvore a
    partir do PGN guardado e a grava."""
    from chess_trainer.core.studies.service import ensure_tree

    engine = make_engine(str(db_do_ciclo_anterior))
    init_db(engine)
    try:
        with make_session_factory(engine)() as db:
            capitulo = db.get(StudyChapter, "c1")
            tree = ensure_tree(capitulo)
            db.commit()
            assert [n["san"] for n in tree["root"]["children"]] == ["e4"]
            assert db.get(StudyChapter, "c1").tree_json
    finally:
        engine.dispose()


# --- coluna da resposta em blocos do treinador ---------------------------


@pytest.fixture
def db_sem_a_resposta_em_blocos(tmp_path):
    """Banco do ciclo anterior do treinador: `coach_explanations` sem o
    `structured_json` (o `DROP COLUMN` do SQLite o tira do banco novo)."""
    path = tmp_path / "treinador.db"
    engine = make_engine(str(path))
    init_db(engine)
    with make_session_factory(engine)() as db:
        db.add(Puzzle(id="pz1", kind="punish", fen_start="fen-do-puzzle", side_to_move="white",
                      solution="[]", end_reason="mate", theme="mate_in_1", category="rapid", solver_moves=1))
        db.flush()
        db.add(CoachExplanation(id="ex1", puzzle_id="pz1", model="claude-opus-5", prompt_version="v2",
                                effort="high", text="explicação antiga", status="ok"))
        db.commit()
    engine.dispose()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE coach_explanations DROP COLUMN structured_json")
    conn.commit()
    conn.close()
    return path


def test_migracao_acrescenta_a_coluna_da_resposta_em_blocos(db_sem_a_resposta_em_blocos):
    assert "structured_json" not in _colunas(db_sem_a_resposta_em_blocos, "coach_explanations")
    engine = make_engine(str(db_sem_a_resposta_em_blocos))
    init_db(engine)
    init_db(engine)  # segunda passada não pode falhar nem duplicar a coluna
    try:
        assert "structured_json" in _colunas(db_sem_a_resposta_em_blocos, "coach_explanations")
        with make_session_factory(engine)() as db:
            antiga = db.get(CoachExplanation, "ex1")
            # a explicação que já existia não se perde e fica sem blocos
            assert antiga is not None and antiga.text == "explicação antiga"
            assert not antiga.structured_json or antiga.structured_json == "{}"
    finally:
        engine.dispose()


def test_migracao_cria_golpes(tmp_path):
    caminho = tmp_path / "old.db"
    con = sqlite3.connect(caminho); con.executescript(OLD_SCHEMA); con.close()
    init_db(make_engine(str(caminho)))
    con = sqlite3.connect(caminho)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(puzzles)")}
    tabelas = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert "sibling_of" in colunas
    assert {"lichess_puzzle_signatures", "puzzle_signatures", "golpe_labels"} <= tabelas


# --- trechos: colunas de procedência e a tabela nova (spec golpes trechos) ----


@pytest.fixture
def db_sem_trechos(tmp_path):
    """Banco já com as tabelas de golpes (fase A), mas de antes dos trechos: sem
    `puzzles.sibling_tier`, sem as colunas de procedência em `golpe_labels` e sem
    `lichess_puzzle_trechos` (o `DROP TABLE`/`DROP COLUMN` do SQLite as tira de um
    banco novo, simulando o estado anterior)."""
    path = tmp_path / "sem_trechos.db"
    engine = make_engine(str(path))
    init_db(engine)
    with make_session_factory(engine)() as db:
        db.add(Puzzle(id="pz1", kind="punish", fen_start="fen-do-puzzle", side_to_move="white",
                      solution="[]", end_reason="mate", theme="mate_in_1", category="rapid", solver_moves=1))
        db.commit()
    engine.dispose()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE puzzles DROP COLUMN sibling_tier")
    conn.execute("ALTER TABLE golpe_labels DROP COLUMN n_lances")
    conn.execute("ALTER TABLE golpe_labels DROP COLUMN posicao")
    conn.execute("ALTER TABLE golpe_labels DROP COLUMN nivel")
    conn.execute("ALTER TABLE golpe_labels DROP COLUMN espelhado")
    conn.execute("DROP TABLE lichess_puzzle_trechos")
    conn.commit()
    conn.close()
    return path


# --- voto: uma linha por par (âncora, candidato) ("o voto mora no bloco") ----


@pytest.fixture
def db_golpe_labels_duplicado(tmp_path):
    """Banco de antes do voto: a rotulagem podia gravar mais de uma linha para o mesmo par
    (âncora, candidato) — sem o índice único que a revisão do voto exige. Recria
    `golpe_labels` sem a `UNIQUE` para simular esse estado e insere duas linhas do mesmo par,
    a mais nova com um rótulo diferente."""
    path = tmp_path / "labels_duplicados.db"
    engine = make_engine(str(path))
    init_db(engine)
    engine.dispose()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE golpe_labels")
    conn.execute("""
        CREATE TABLE golpe_labels (
            id VARCHAR(36) NOT NULL,
            anchor_origem VARCHAR(8) NOT NULL,
            anchor_id VARCHAR(36) NOT NULL,
            candidate_id VARCHAR(8) NOT NULL,
            tier_na_hora VARCHAR(16) NOT NULL,
            versao_assinatura INTEGER NOT NULL,
            label VARCHAR(8) NOT NULL,
            created_at DATETIME NOT NULL,
            n_lances INTEGER,
            posicao VARCHAR(8),
            nivel VARCHAR(10),
            espelhado BOOLEAN,
            PRIMARY KEY (id)
        )
    """)
    conn.execute(
        "INSERT INTO golpe_labels VALUES ('l1','lichess','a','b','inteira',2,'nada','2026-09-01 10:00:00',NULL,NULL,NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO golpe_labels VALUES ('l2','lichess','a','b','inteira',2,'mesmo','2026-09-02 10:00:00',NULL,NULL,NULL,NULL)"
    )
    # um par diferente, sem duplicata: não pode sumir na limpeza
    conn.execute(
        "INSERT INTO golpe_labels VALUES ('l3','lichess','a','c','inteira',2,'nada','2026-09-01 10:00:00',NULL,NULL,NULL,NULL)"
    )
    conn.commit()
    conn.close()
    return path


def test_migracao_deduplica_golpe_labels_mantendo_o_mais_novo(db_golpe_labels_duplicado):
    engine = make_engine(str(db_golpe_labels_duplicado))
    init_db(engine)
    try:
        conn = sqlite3.connect(db_golpe_labels_duplicado)
        linhas = conn.execute(
            "SELECT id, label FROM golpe_labels WHERE anchor_id='a' AND candidate_id='b'"
        ).fetchall()
        total = conn.execute("SELECT count(*) FROM golpe_labels").fetchone()[0]
        indices = {row[1] for row in conn.execute("PRAGMA index_list(golpe_labels)")}
        conn.close()
        assert linhas == [("l2", "mesmo")]  # o mais novo venceu
        assert total == 2  # a duplicata some, o par "a"/"c" fica
        assert "uq_golpe_labels_par" in indices
    finally:
        engine.dispose()


def test_migracao_deduplica_golpe_labels_e_e_idempotente(db_golpe_labels_duplicado):
    engine = make_engine(str(db_golpe_labels_duplicado))
    init_db(engine)
    init_db(engine)
    try:
        conn = sqlite3.connect(db_golpe_labels_duplicado)
        total = conn.execute("SELECT count(*) FROM golpe_labels").fetchone()[0]
        conn.close()
        assert total == 2
    finally:
        engine.dispose()


def test_migracao_cria_o_indice_unico_num_banco_novo(tmp_path):
    """Banco criado do zero já tem a `UniqueConstraint` do modelo: o `CREATE UNIQUE INDEX IF
    NOT EXISTS` da migração não pode falhar por cima dela (mesmo nome)."""
    path = tmp_path / "novo.db"
    engine = make_engine(str(path))
    init_db(engine)
    init_db(engine)
    try:
        conn = sqlite3.connect(path)
        indices = {row[1] for row in conn.execute("PRAGMA index_list(golpe_labels)")}
        conn.close()
        assert "uq_golpe_labels_par" in indices
    finally:
        engine.dispose()


def test_migracao_acrescenta_as_colunas_e_a_tabela_dos_trechos(db_sem_trechos):
    assert "sibling_tier" not in _colunas(db_sem_trechos, "puzzles")
    assert "lichess_puzzle_trechos" not in {
        r[0] for r in sqlite3.connect(db_sem_trechos).execute("select name from sqlite_master where type='table'")
    }
    engine = make_engine(str(db_sem_trechos))
    init_db(engine)
    init_db(engine)  # idempotente
    try:
        assert "sibling_tier" in _colunas(db_sem_trechos, "puzzles")
        assert {"n_lances", "posicao", "nivel", "espelhado"} <= _colunas(db_sem_trechos, "golpe_labels")
        tabelas = {r[0] for r in sqlite3.connect(db_sem_trechos).execute("select name from sqlite_master where type='table'")}
        assert "lichess_puzzle_trechos" in tabelas
        with make_session_factory(engine)() as db:
            puzzle = db.get(Puzzle, "pz1")
            assert puzzle is not None and puzzle.sibling_tier is None
    finally:
        engine.dispose()
