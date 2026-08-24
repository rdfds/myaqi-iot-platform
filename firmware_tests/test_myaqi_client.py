from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "AdafruitCode"))

from myaqi_backend.auth import (  # noqa: E402
    derive_device_secret,
    encode_device_secret,
    verify_request_signature,
)
from myaqi_backend.auth import (  # noqa: E402
    sign_request as backend_sign_request,
)
from myaqi_client import JsonStateStore, MyAQIClient, UploadError, sign_request  # noqa: E402

DEVICE_ID = "school-001"
MASTER_KEY = "firmware-test-master-key-with-32-characters"
SECRET = derive_device_secret(MASTER_KEY, DEVICE_ID)
ENCODED_SECRET = encode_device_secret(SECRET)
NOW = 1_787_500_000


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        self.closed = False

    def json(self):
        return self.payload

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []
        self.responses = []

    def post(self, url, data, headers, timeout):
        self.calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        response = self.responder(url, data, headers)
        self.responses.append(response)
        return response


class FailingStore:
    def save(self, _state):
        raise OSError("simulated flash write failure")


def make_client(tmp_path, session, *, batch_size=20, max_pending=120):
    return MyAQIClient(
        session,
        "http://localhost:8000",
        DEVICE_ID,
        ENCODED_SECRET,
        JsonStateStore(str(tmp_path / "state.json")),
        batch_size=batch_size,
        max_pending=max_pending,
        time_fn=lambda: NOW,
    )


def test_circuitpython_hmac_matches_backend_protocol() -> None:
    body = b'{"readings":[]}'
    path = f"/v1/devices/{DEVICE_ID}/measurements:batch"

    assert sign_request(SECRET, str(NOW), "POST", path, body) == backend_sign_request(
        SECRET, str(NOW), "POST", path, body
    )


def test_flush_signs_exact_body_and_removes_acknowledged_readings(tmp_path) -> None:
    def accept(_url, body, headers):
        path = f"/v1/devices/{DEVICE_ID}/measurements:batch"
        verify_request_signature(
            secret=SECRET,
            timestamp=headers["X-Device-Timestamp"],
            signature=headers["X-Device-Signature"],
            method="POST",
            path=path,
            body=body,
            max_clock_skew_seconds=300,
            now=NOW,
        )
        readings = json.loads(body)["readings"]
        return FakeResponse(202, {"accepted": len(readings), "duplicates": 0})

    session = FakeSession(accept)
    client = make_client(tmp_path, session, batch_size=2)
    client.enqueue(12.5, observed_at="2026-08-23T14:30:00Z")
    client.enqueue(13.1, observed_at="2026-08-23T14:31:00Z")

    result = client.flush()

    assert result == {"accepted": 2, "duplicates": 0, "remaining": 0}
    assert client.pending_count == 0
    assert session.calls[0]["headers"]["Idempotency-Key"] == "myaqi-batch-school-001-1-2"
    assert session.responses[0].closed is True
    assert JsonStateStore(str(tmp_path / "state.json")).load()["pending"] == []


def test_failed_upload_keeps_reading_for_next_boot(tmp_path) -> None:
    session = FakeSession(lambda _url, _body, _headers: FakeResponse(503, {}))
    client = make_client(tmp_path, session)
    client.enqueue(18.2, observed_at="2026-08-23T14:30:00Z")

    with pytest.raises(UploadError, match="HTTP 503"):
        client.flush()

    assert client.pending_count == 1
    assert session.responses[0].closed is True
    reloaded = make_client(tmp_path, session)
    assert reloaded.pending_count == 1
    assert reloaded.state["pending"][0]["sequence"] == 1


def test_duplicate_acknowledgement_clears_retried_reading(tmp_path) -> None:
    session = FakeSession(
        lambda _url, _body, _headers: FakeResponse(202, {"accepted": 0, "duplicates": 1})
    )
    client = make_client(tmp_path, session)
    client.enqueue(10.0, observed_at="2026-08-23T14:30:00Z")

    result = client.flush()

    assert result == {"accepted": 0, "duplicates": 1, "remaining": 0}
    assert client.pending_count == 0


def test_queue_limit_is_explicit_and_counts_dropped_readings(tmp_path) -> None:
    session = FakeSession(lambda _url, _body, _headers: FakeResponse(202, {}))
    client = make_client(tmp_path, session, batch_size=1, max_pending=2)

    for value in (10.0, 11.0, 12.0):
        client.enqueue(value, observed_at="2026-08-23T14:30:00Z")

    assert [item["sequence"] for item in client.state["pending"]] == [2, 3]
    assert client.state["dropped_readings"] == 1


def test_state_store_recovers_last_complete_backup(tmp_path) -> None:
    store = JsonStateStore(str(tmp_path / "state.json"))
    first = {
        "next_sequence": 2,
        "pending": [
            {
                "sequence": 1,
                "observed_at": "2026-08-23T14:30:00Z",
                "pm25_ug_m3": 12.0,
            }
        ],
        "dropped_readings": 0,
    }
    second = {
        "next_sequence": 3,
        "pending": [
            {
                "sequence": 2,
                "observed_at": "2026-08-23T14:31:00Z",
                "pm25_ug_m3": 13.0,
            }
        ],
        "dropped_readings": 0,
    }
    store.save(first)
    store.save(second)
    (tmp_path / "state.json").write_text("not-json", encoding="utf-8")

    assert store.load() == first


def test_state_store_rejects_non_object_state(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="No valid ingestion state"):
        JsonStateStore(str(path)).load()


def test_state_store_rejects_queue_that_can_reuse_a_sequence(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "next_sequence": 1,
                "pending": [
                    {
                        "sequence": 1,
                        "observed_at": "2026-08-23T14:30:00Z",
                        "pm25_ug_m3": 12.0,
                    }
                ],
                "dropped_readings": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="No valid ingestion state"):
        JsonStateStore(str(path)).load()


@pytest.mark.parametrize("value", [-0.1, 5000.1, float("nan")])
def test_invalid_sensor_value_is_not_persisted(tmp_path, value) -> None:
    session = FakeSession(lambda _url, _body, _headers: FakeResponse(202, {}))
    client = make_client(tmp_path, session)

    with pytest.raises(ValueError, match="between 0 and 5000"):
        client.enqueue(value, observed_at="2026-08-23T14:30:00Z")

    assert client.pending_count == 0
    assert client.state["next_sequence"] == 1


def test_plaintext_lookalike_host_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="HTTPS origin"):
        MyAQIClient(
            FakeSession(lambda _url, _body, _headers: FakeResponse(202, {})),
            "http://localhost.attacker.example",
            DEVICE_ID,
            ENCODED_SECRET,
            JsonStateStore(str(tmp_path / "state.json")),
        )


def test_failed_acknowledgement_checkpoint_keeps_in_memory_queue(tmp_path) -> None:
    session = FakeSession(
        lambda _url, _body, _headers: FakeResponse(202, {"accepted": 1, "duplicates": 0})
    )
    client = make_client(tmp_path, session)
    client.enqueue(12.0, observed_at="2026-08-23T14:30:00Z")
    client.state_store = FailingStore()

    with pytest.raises(OSError, match="flash write failure"):
        client.flush()

    assert client.pending_count == 1
    assert client.state["pending"][0]["sequence"] == 1


def test_failed_enqueue_checkpoint_does_not_advance_sequence(tmp_path) -> None:
    session = FakeSession(lambda _url, _body, _headers: FakeResponse(202, {}))
    client = make_client(tmp_path, session)
    client.state_store = FailingStore()

    with pytest.raises(OSError, match="flash write failure"):
        client.enqueue(12.0, observed_at="2026-08-23T14:30:00Z")

    assert client.pending_count == 0
    assert client.state["next_sequence"] == 1
