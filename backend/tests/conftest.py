import pytest
from sqlalchemy.orm import Session

from chess_trainer.core.db import init_db, make_engine, make_session_factory


@pytest.fixture
def db_engine():
    engine = make_engine(":memory:")
    init_db(engine)
    return engine


@pytest.fixture
def db_session(db_engine) -> Session:
    factory = make_session_factory(db_engine)
    with factory() as session:
        yield session
