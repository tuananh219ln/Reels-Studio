from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # connect_timeout keeps a stopped Postgres from hanging requests; the API answers 503 instead.
    return create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})


def get_db() -> Iterator[Session]:
    with sessionmaker(get_engine(), expire_on_commit=False)() as session:
        yield session
