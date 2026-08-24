from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "AdafruitCode"))

from myaqi_backend import create_app  # noqa: E402
from myaqi_backend.auth import derive_device_secret, encode_device_secret  # noqa: E402
from myaqi_backend.database import Base, make_engine  # noqa: E402
from myaqi_backend.models import (  # noqa: E402
    Device,
    IngestRequest,
    Measurement,
    OutboxEvent,
)
from myaqi_client import JsonStateStore, MyAQIClient  # noqa: E402

DEVICE_ID = "school-001"
MASTER_KEY = "firmware-end-to-end-master-key-with-32-characters"


class CircuitPythonResponseAdapter:
    def __init__(self, response):
        self.status_code = response.status_code
        self._payload = response.get_json()
        self.closed = False

    def json(self):
        return self._payload

    def close(self):
        self.closed = True


class FlaskSessionAdapter:
    """Expose Flask's test client through the subset used by adafruit_requests."""

    def __init__(self, flask_client, *, drop_response_once=False):
        self.flask_client = flask_client
        self.drop_response_once = drop_response_once
        self.last_headers = None

    def post(self, url, data, headers, timeout):
        del timeout
        path = url.removeprefix("http://localhost:8000")
        response = self.flask_client.post(path, data=data, headers=headers)
        self.last_headers = response.headers
        if self.drop_response_once:
            self.drop_response_once = False
            raise OSError("simulated connection loss after server commit")
        return CircuitPythonResponseAdapter(response)


def test_lost_response_replays_without_duplicate_measurement_or_event(tmp_path) -> None:
    engine = make_engine("sqlite+pysqlite://", testing=True)
    Base.metadata.create_all(engine)
    app = create_app(
        {
            "TESTING": True,
            "DEVICE_MASTER_KEY": MASTER_KEY,
            "AUTH_CLOCK_SKEW_SECONDS": 300,
            "LOG_LEVEL": "WARNING",
        },
        engine=engine,
    )
    session_factory = app.extensions["myaqi_session_factory"]
    with session_factory() as session, session.begin():
        session.add(Device(id=DEVICE_ID, display_name="Test classroom"))

    state_store = JsonStateStore(str(tmp_path / "device-state.json"))
    secret = encode_device_secret(derive_device_secret(MASTER_KEY, DEVICE_ID))
    first_session = FlaskSessionAdapter(app.test_client(), drop_response_once=True)
    firmware = MyAQIClient(
        first_session,
        "http://localhost:8000",
        DEVICE_ID,
        secret,
        state_store,
        time_fn=time.time,
    )
    firmware.enqueue(12.7, observed_at="2026-08-23T14:30:00Z")

    with pytest.raises(OSError, match="after server commit"):
        firmware.flush()
    assert firmware.pending_count == 1

    retry_session = FlaskSessionAdapter(app.test_client())
    rebooted_firmware = MyAQIClient(
        retry_session,
        "http://localhost:8000",
        DEVICE_ID,
        secret,
        state_store,
        time_fn=time.time,
    )
    result = rebooted_firmware.flush()

    assert result == {"accepted": 1, "duplicates": 0, "remaining": 0}
    assert retry_session.last_headers["Idempotent-Replayed"] == "true"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(IngestRequest)) == 1
        assert session.scalar(select(func.count()).select_from(Measurement)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    engine.dispose()
