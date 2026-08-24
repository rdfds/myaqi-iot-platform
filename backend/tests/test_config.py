from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from myaqi_backend.config import database_url_from_env


def test_database_url_assembles_managed_secret_components(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "database.internal")
    monkeypatch.setenv("DB_NAME", "myaqi")
    monkeypatch.setenv("DB_USER", "service-user")
    monkeypatch.setenv("DB_PASSWORD", "password with:/? symbols")

    url = make_url(database_url_from_env())

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "service-user"
    assert url.password == "password with:/? symbols"
    assert url.host == "database.internal"
    assert url.port == 5432
    assert url.database == "myaqi"


def test_explicit_database_url_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://explicit/db")
    monkeypatch.setenv("DB_HOST", "ignored.internal")
    assert database_url_from_env() == "postgresql+psycopg://explicit/db"


def test_partial_managed_database_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "database.internal")
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="name, user, password"):
        database_url_from_env()
