from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import Engine

from myaqi_backend import create_app
from myaqi_backend.auth import derive_device_secret, sign_request
from myaqi_backend.database import Base, make_engine
from myaqi_backend.models import Device

TEST_MASTER_KEY = "test-device-master-key-with-at-least-32-characters"
DEVICE_ID = "school-001"


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite://")


@pytest.fixture()
def engine(database_url: str) -> Iterator[Engine]:
    engine = make_engine(database_url, testing=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def app(engine: Engine) -> Flask:
    app = create_app(
        {
            "TESTING": True,
            "DEVICE_MASTER_KEY": TEST_MASTER_KEY,
            "AUTH_CLOCK_SKEW_SECONDS": 300,
            "MAX_BATCH_SIZE": 500,
            "LOG_LEVEL": "WARNING",
        },
        engine=engine,
    )
    factory = app.extensions["myaqi_session_factory"]
    with factory() as session, session.begin():
        session.add(Device(id=DEVICE_ID, display_name="Test classroom"))
    return app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture()
def signed_post() -> Callable[..., object]:
    def post(
        client: FlaskClient,
        payload: dict[str, object],
        *,
        device_id: str = DEVICE_ID,
        idempotency_key: str = "request-0000000001",
        timestamp: str | None = None,
        secret: bytes | None = None,
    ):
        path = f"/v1/devices/{device_id}/measurements:batch"
        body = json.dumps(payload, separators=(",", ":")).encode()
        request_timestamp = timestamp or str(int(time.time()))
        device_secret = secret or derive_device_secret(TEST_MASTER_KEY, device_id)
        signature = sign_request(device_secret, request_timestamp, "POST", path, body)
        return client.post(
            path,
            data=body,
            content_type="application/json",
            headers={
                "Idempotency-Key": idempotency_key,
                "X-Device-Timestamp": request_timestamp,
                "X-Device-Signature": signature,
            },
        )

    return post


@pytest.fixture()
def measurement_batch() -> dict[str, object]:
    return {
        "readings": [
            {
                "sequence": 101,
                "observed_at": "2026-08-23T14:30:00Z",
                "pm25_ug_m3": 12.7,
                "temperature_c": 22.4,
                "relative_humidity": 44.1,
            },
            {
                "sequence": 102,
                "observed_at": "2026-08-23T14:31:00Z",
                "pm25_ug_m3": 13.1,
            },
        ]
    }
