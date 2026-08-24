from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


SessionFactory = sessionmaker[Session]


def make_engine(database_url: str, *, testing: bool = False) -> Engine:
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url in {"sqlite://", "sqlite+pysqlite://"}:
        options.update(
            {
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            }
        )
    elif database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}

    if testing:
        options["echo"] = False
    return create_engine(database_url, **options)


def make_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def transactional_session(factory: SessionFactory) -> Iterator[Session]:
    with factory() as session, session.begin():
        yield session
