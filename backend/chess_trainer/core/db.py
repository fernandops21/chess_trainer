import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable

from chess_trainer.core.models import Base, Puzzle


def _carregar_sqlite_vec(dbapi_conn) -> None:
    """Carrega a extensão `sqlite-vec` na conexão; sem o pacote, sem suporte a
    extensões ou com erro de carga, a busca vetorial cai no numpy (ver
    `coach/retrieval/store.py`)."""
    try:
        import sqlite_vec
    except ImportError:
        return
    try:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
    except Exception:  # noqa: BLE001 - AttributeError (sem extensões) ou OperationalError
        return
    finally:
        try:
            dbapi_conn.enable_load_extension(False)
        except AttributeError:
            pass


def vec_disponivel(engine: Engine) -> bool:
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("SELECT vec_version()").scalar()
            return True
        except Exception:  # noqa: BLE001
            return False


def make_engine(db_path: str | None) -> Engine:
    is_file = db_path is not None and db_path != ":memory:"
    if not is_file:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            f"sqlite:///{db_path}",
            # timeout generoso: o job de análise ainda pode escrever em rajadas
            connect_args={"check_same_thread": False, "timeout": 30},
        )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        _carregar_sqlite_vec(dbapi_conn)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        if is_file:
            # WAL: leitores não bloqueiam o escritor (a API continua respondendo durante um job)
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


# Colunas acrescentadas a `puzzles` no ciclo das fontes de exercício, com o
# padrão que os puzzles já existentes recebem (todos viram `own` e ficam na fila).
_NEW_PUZZLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("source", "VARCHAR(8) NOT NULL DEFAULT 'own'"),
    ("in_queue", "BOOLEAN NOT NULL DEFAULT 1"),
    ("external_id", "VARCHAR(16)"),
    ("chapter_id", "VARCHAR(36)"),
    ("fen_before", "VARCHAR(100)"),
    ("last_move", "VARCHAR(6)"),
)

# Colunas acrescentadas a `studies` e `study_chapters` no ciclo do editor de
# estudos. Só ADD COLUMN: nenhuma tabela é refeita. Os estudos que já existiam
# vieram do Lichess (daí o padrão de `origin`), e o `updated_at`/`tree_json` dos
# capítulos antigos fica vazio até a primeira leitura no editor.
_NEW_STUDY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("origin", "VARCHAR(8) NOT NULL DEFAULT 'lichess'"),
    ("updated_at", "DATETIME"),
)
_NEW_CHAPTER_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tree_json", "TEXT"),
    ("updated_at", "DATETIME"),
)

# Coluna acrescentada a `coach_explanations` no ciclo da resposta em blocos. As
# explicações que já existiam não têm blocos: ficam com `{}` e o cartão cai no `text`.
_NEW_COACH_EXPLANATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("structured_json", "TEXT NOT NULL DEFAULT '{}'"),
)

# Coluna acrescentada a `puzzles` no ciclo dos golpes: o vínculo do exercício de
# origem quando este entrou pelo bloco "Repetir o golpe" (spec golpes §6). O
# SQLite não aceita FK num ADD COLUMN; a referência a `puzzles.id` vive só no modelo.
_NEW_GOLPES_PUZZLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sibling_of", "VARCHAR(36)"),
)

# Coluna acrescentada a `puzzles` no ciclo dos trechos: o degrau da cascata que
# trouxe o irmão (spec golpes trechos §6).
_NEW_GOLPES_TRECHOS_PUZZLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sibling_tier", "VARCHAR(24)"),
)

# Colunas acrescentadas a `golpe_labels` no ciclo dos trechos: a procedência do
# candidato na hora do julgamento (spec golpes trechos §8).
_NEW_GOLPES_TRECHOS_LABEL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("n_lances", "INTEGER"),
    ("posicao", "VARCHAR(8)"),
    ("nivel", "VARCHAR(10)"),
    ("espelhado", "BOOLEAN"),
)

# Índices de `puzzles` que não saem de um `CREATE INDEX` do metadata: o
# `uq_puzzle_fen_kind_source` acompanha a `UniqueConstraint` declarada dentro do
# `CREATE TABLE`, e num banco antigo a tabela já existe quando o `create_all` roda.
_PUZZLE_INDEXES: tuple[str, ...] = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_puzzle_fen_kind_source ON puzzles (fen_start, kind, source)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_puzzle_external_id ON puzzles (external_id)",
    "CREATE INDEX IF NOT EXISTS ix_puzzles_source ON puzzles (source)",
    "CREATE INDEX IF NOT EXISTS ix_puzzles_in_queue ON puzzles (in_queue)",
    "CREATE INDEX IF NOT EXISTS ix_puzzles_chapter_id ON puzzles (chapter_id)",
)

# Colunas cujo NOT NULL do esquema antigo impede um puzzle de fonte externa
# (Lichess ou estudo), que não tem partida nem posição de origem.
_PUZZLE_COLUMNS_NULLABLE_AGORA: tuple[str, ...] = ("position_id", "game_id")


def _acrescenta_colunas(conn, tabela: str, colunas: tuple[tuple[str, str], ...]) -> None:
    """ALTER TABLE ADD COLUMN para o que faltar. Tabela ausente: nada a fazer."""
    existentes = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({tabela})")}
    if not existentes:
        return
    for nome, ddl in colunas:
        if nome not in existentes:
            conn.exec_driver_sql(f"ALTER TABLE {tabela} ADD COLUMN {nome} {ddl}")


def _puzzles_no_esquema_antigo(engine: Engine) -> bool:
    """A tabela `puzzles` ainda exige `position_id`/`game_id`? O SQLite não tira
    um NOT NULL (nem a única antiga `(fen_start, kind)`) por ALTER TABLE."""
    with engine.connect() as conn:
        return any(
            row[1] in _PUZZLE_COLUMNS_NULLABLE_AGORA and row[3] == 1
            for row in conn.exec_driver_sql("PRAGMA table_info(puzzles)")
        )


def _copia_de_seguranca(engine: Engine) -> None:
    """Cópia do arquivo do banco antes de mexer na estrutura de `puzzles`.
    Banco em memória não tem arquivo e é ignorado."""
    caminho = engine.url.database
    if not caminho or caminho == ":memory:":
        return
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        # sem o checkpoint, o que estiver no WAL ficaria de fora da cópia; se outro
        # leitor segura o WAL, a cópia sairia velha sem aviso — melhor parar.
        busy = conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").first()
        if busy is not None and busy[0]:
            raise RuntimeError("não foi possível fazer o checkpoint do banco antes da cópia de segurança; feche outros acessos e tente de novo")
    origem = Path(caminho)
    destino = origem.with_name(f"{origem.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(origem, destino)


def _reconstruir_puzzles(engine: Engine) -> None:
    """Refaz `puzzles` no esquema atual pelo procedimento que o SQLite documenta
    para mudanças que o ALTER TABLE não alcança: cria a tabela nova a partir do
    metadata, copia todas as linhas, apaga a antiga e renomeia. As colunas novas
    ficam com o padrão; nenhum puzzle e nenhuma revisão se perde."""
    ddl_tabela = str(CreateTable(Puzzle.__table__).compile(engine))
    ddl_tabela = ddl_tabela.replace("CREATE TABLE puzzles ", "CREATE TABLE puzzles_new ", 1)
    ddl_indices = [str(CreateIndex(indice).compile(engine)).strip() for indice in Puzzle.__table__.indexes]

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        antigas = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(puzzles)")}
        comuns = ", ".join(coluna.name for coluna in Puzzle.__table__.columns if coluna.name in antigas)
        # o PRAGMA é ignorado dentro de uma transação: daí o modo autocommit
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.exec_driver_sql("BEGIN")
        try:
            conn.exec_driver_sql(ddl_tabela)
            conn.exec_driver_sql(f"INSERT INTO puzzles_new ({comuns}) SELECT {comuns} FROM puzzles")
            conn.exec_driver_sql("DROP TABLE puzzles")
            conn.exec_driver_sql("ALTER TABLE puzzles_new RENAME TO puzzles")
            for ddl in ddl_indices:
                conn.exec_driver_sql(ddl)
            # `reviews.puzzle_id` e `study_chapters.puzzle_id` apontam para o nome
            # `puzzles`, que o rename devolve; o check confirma antes do commit
            quebradas = list(conn.exec_driver_sql("PRAGMA foreign_key_check"))
            if quebradas:
                raise RuntimeError(f"migração de `puzzles`: {len(quebradas)} referência(s) quebrada(s)")
            conn.exec_driver_sql("COMMIT")
        except Exception:
            conn.exec_driver_sql("ROLLBACK")
            raise
        finally:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def migrate(engine: Engine) -> None:
    """Acrescenta a bancos antigos o que o `create_all` não alcança: colunas,
    índices e o esquema atual de `puzzles`. Nenhum puzzle ou histórico é apagado.
    Idempotente — rodar de novo (ou num banco criado do zero) não faz nada."""
    with engine.connect() as conn:
        # chamada solta (fora do `init_db`) num banco ainda sem tabelas: nada a fazer
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(puzzles)")}
    if not existing:
        return
    # a cópia de segurança sai antes de qualquer alteração de estrutura
    esquema_antigo = _puzzles_no_esquema_antigo(engine)
    if esquema_antigo:
        _copia_de_seguranca(engine)

    with engine.begin() as conn:
        for name, ddl in _NEW_PUZZLE_COLUMNS:
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE puzzles ADD COLUMN {name} {ddl}")

    if esquema_antigo:
        _reconstruir_puzzles(engine)

    with engine.begin() as conn:
        for statement in _PUZZLE_INDEXES:
            conn.exec_driver_sql(statement)
        _acrescenta_colunas(conn, "studies", _NEW_STUDY_COLUMNS)
        _acrescenta_colunas(conn, "study_chapters", _NEW_CHAPTER_COLUMNS)
        _acrescenta_colunas(conn, "coach_explanations", _NEW_COACH_EXPLANATION_COLUMNS)
        _acrescenta_colunas(conn, "puzzles", _NEW_GOLPES_PUZZLE_COLUMNS)
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_puzzles_sibling_of ON puzzles (sibling_of)")
        _acrescenta_colunas(conn, "puzzles", _NEW_GOLPES_TRECHOS_PUZZLE_COLUMNS)
        _acrescenta_colunas(conn, "golpe_labels", _NEW_GOLPES_TRECHOS_LABEL_COLUMNS)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    migrate(engine)
