from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chess_trainer.core.models import Base


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

# Índices de `puzzles` que o `create_all` não cria em banco antigo (a tabela já
# existe). O SQLite não remove a restrição única antiga `(fen_start, kind)`
# declarada dentro do CREATE TABLE; ela fica e não atrapalha, porque puzzles
# `lichess`/`study` não disputam posição com os erros das partidas do usuário.
_PUZZLE_INDEXES: tuple[str, ...] = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_puzzle_fen_kind_source ON puzzles (fen_start, kind, source)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_puzzle_external_id ON puzzles (external_id)",
    "CREATE INDEX IF NOT EXISTS ix_puzzles_source ON puzzles (source)",
    "CREATE INDEX IF NOT EXISTS ix_puzzles_in_queue ON puzzles (in_queue)",
    "CREATE INDEX IF NOT EXISTS ix_puzzles_chapter_id ON puzzles (chapter_id)",
)


def migrate(engine: Engine) -> None:
    """Acrescenta a bancos antigos o que o `create_all` não alcança. Só adiciona
    colunas e índices: nenhum puzzle ou histórico é apagado ou reescrito.
    Idempotente — rodar de novo (ou num banco criado do zero) não faz nada."""
    with engine.begin() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(puzzles)")}
        if not existing:  # banco sem a tabela: o create_all já deu conta
            return
        for name, ddl in _NEW_PUZZLE_COLUMNS:
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE puzzles ADD COLUMN {name} {ddl}")
        for statement in _PUZZLE_INDEXES:
            conn.exec_driver_sql(statement)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    migrate(engine)
