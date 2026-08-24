from __future__ import annotations

import json
import time

from myaqi_backend.auth import derive_device_secret, sign_request
from tests.conftest import TEST_MASTER_KEY
from tests.test_ingestion import counts


def signed_raw(client, *, device_id: str, raw_body: bytes, idempotency_key: str):
    path = f"/v1/devices/{device_id}/measurements:batch"
    timestamp = str(int(time.time()))
    signature = sign_request(
        derive_device_secret(TEST_MASTER_KEY, device_id),
        timestamp,
        "POST",
        path,
        raw_body,
    )
    return client.post(
        path,
        data=raw_body,
        content_type="application/json",
        headers={
            "Idempotency-Key": idempotency_key,
            "X-Device-Timestamp": timestamp,
            "X-Device-Signature": signature,
        },
    )


def test_unknown_device_and_bad_signature_have_same_public_error(
    app, client, signed_post, measurement_batch
) -> None:
    unknown = signed_post(client, measurement_batch, device_id="unknown-device")
    invalid = signed_post(client, measurement_batch, secret=b"wrong-secret")

    assert unknown.status_code == invalid.status_code == 401
    assert unknown.get_json()["detail"] == invalid.get_json()["detail"]
    assert unknown.get_json()["type"] == invalid.get_json()["type"]
    assert counts(app) == (0, 0, 0)


def test_invalid_json_returns_problem_response_without_writes(app, client) -> None:
    response = signed_raw(
        client,
        device_id="school-001",
        raw_body=b'{"readings":',
        idempotency_key="request-invalid-json",
    )

    assert response.status_code == 422
    assert response.is_json
    assert response.get_json()["type"].endswith("/invalid_batch")
    assert counts(app) == (0, 0, 0)


def test_duplicate_sequence_inside_batch_is_rejected(app, client, measurement_batch) -> None:
    duplicate = {
        "readings": [
            measurement_batch["readings"][0],
            {**measurement_batch["readings"][1], "sequence": 101},
        ]
    }
    body = json.dumps(duplicate, separators=(",", ":")).encode()

    response = signed_raw(
        client,
        device_id="school-001",
        raw_body=body,
        idempotency_key="request-duplicate-seq",
    )

    assert response.status_code == 422
    assert "duplicate sequence 101" in response.get_json()["detail"]
    assert counts(app) == (0, 0, 0)


def test_batch_size_limit_is_enforced(app, client, measurement_batch) -> None:
    app.config["MAX_BATCH_SIZE"] = 1
    body = json.dumps(measurement_batch, separators=(",", ":")).encode()

    response = signed_raw(
        client,
        device_id="school-001",
        raw_body=body,
        idempotency_key="request-too-many-rows",
    )

    assert response.status_code == 422
    assert "at most 1 items" in response.get_json()["detail"]
    assert counts(app) == (0, 0, 0)


def test_idempotency_key_format_is_checked_before_processing(client) -> None:
    response = client.post(
        "/v1/devices/school-001/measurements:batch",
        data=b"{}",
        content_type="application/json",
        headers={"Idempotency-Key": "short"},
    )

    assert response.status_code == 400
    assert response.get_json()["type"].endswith("/invalid_idempotency_key")


def test_firmware_version_header_rejects_unsafe_identifier(
    client, signed_post, measurement_batch
) -> None:
    response = signed_post(
        client,
        measurement_batch,
        firmware_version="release candidate/../../latest",
    )

    assert response.status_code == 400
    assert response.get_json()["type"].endswith("/invalid_firmware_version")
