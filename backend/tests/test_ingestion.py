from __future__ import annotations

import time

from sqlalchemy import func, select

from myaqi_backend.models import IngestRequest, Measurement, OutboxEvent


def counts(app) -> tuple[int, int, int]:
    factory = app.extensions["myaqi_session_factory"]
    with factory() as session:
        return (
            session.scalar(select(func.count()).select_from(IngestRequest)),
            session.scalar(select(func.count()).select_from(Measurement)),
            session.scalar(select(func.count()).select_from(OutboxEvent)),
        )


def test_accepts_signed_batch_and_creates_outbox(
    app, client, signed_post, measurement_batch
) -> None:
    response = signed_post(client, measurement_batch)

    assert response.status_code == 202
    assert response.get_json() == {
        "request_id": response.get_json()["request_id"],
        "device_id": "school-001",
        "accepted": 2,
        "duplicates": 0,
    }
    assert response.headers["X-Request-ID"]
    assert counts(app) == (1, 2, 1)


def test_same_idempotency_key_replays_original_response(
    app, client, signed_post, measurement_batch
) -> None:
    first = signed_post(client, measurement_batch)
    second = signed_post(client, measurement_batch)

    assert second.status_code == 202
    assert second.get_json() == first.get_json()
    assert second.headers["Idempotent-Replayed"] == "true"
    assert counts(app) == (1, 2, 1)


def test_reusing_idempotency_key_with_new_payload_conflicts(
    app, client, signed_post, measurement_batch
) -> None:
    assert signed_post(client, measurement_batch).status_code == 202
    changed = {"readings": [{**measurement_batch["readings"][0], "pm25_ug_m3": 99.0}]}

    response = signed_post(client, changed)

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("/idempotency_conflict")
    assert counts(app) == (1, 2, 1)


def test_sequence_deduplication_survives_new_request_key(
    app, client, signed_post, measurement_batch
) -> None:
    assert signed_post(client, measurement_batch).status_code == 202

    response = signed_post(
        client,
        measurement_batch,
        idempotency_key="request-0000000002",
    )

    assert response.status_code == 202
    assert response.get_json()["accepted"] == 0
    assert response.get_json()["duplicates"] == 2
    assert counts(app) == (2, 2, 2)


def test_stale_authentication_is_rejected_without_writes(
    app, client, signed_post, measurement_batch
) -> None:
    response = signed_post(
        client,
        measurement_batch,
        timestamp=str(int(time.time()) - 301),
    )

    assert response.status_code == 401
    assert response.get_json()["type"].endswith("/authentication_failed")
    assert counts(app) == (0, 0, 0)


def test_payload_validation_happens_before_persistence(
    app, client, signed_post, measurement_batch
) -> None:
    invalid = {
        "readings": [
            {
                **measurement_batch["readings"][0],
                "relative_humidity": 101,
            }
        ]
    }

    response = signed_post(client, invalid)

    assert response.status_code == 422
    assert "relative_humidity" in response.get_json()["detail"]
    assert counts(app) == (0, 0, 0)


def test_health_and_metrics_endpoints(client, signed_post, measurement_batch) -> None:
    assert client.get("/health/live").get_json() == {
        "status": "ok",
        "service": "myaqi-api",
        "version": "0.1.0-dev",
        "revision": "local",
        "environment": "development",
    }
    assert client.get("/health/ready").get_json() == {
        "status": "ready",
        "revision": "local",
    }
    signed_post(client, measurement_batch)

    metrics = client.get("/metrics")

    assert metrics.status_code == 200
    assert b'myaqi_ingest_requests_total{outcome="accepted"} 1.0' in metrics.data
    assert b'myaqi_ingested_readings_total{outcome="accepted"} 2.0' in metrics.data
