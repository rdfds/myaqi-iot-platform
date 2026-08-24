from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.exceptions import BadRequest

from myaqi_backend.auth import (
    AuthenticationError,
    body_sha256,
    derive_device_secret,
    verify_request_signature,
)
from myaqi_backend.errors import ApiError
from myaqi_backend.metrics import Metrics
from myaqi_backend.models import Device, IngestRequest, Measurement, OutboxEvent, new_id
from myaqi_backend.validation import PayloadError, ReadingInput, parse_batch

blueprint = Blueprint("ingestion", __name__)
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")


def _metrics() -> Metrics:
    return current_app.extensions["myaqi_metrics"]


def _insert_ingest_request(
    session: Session,
    *,
    device_id: str,
    idempotency_key: str,
    payload_digest: str,
) -> tuple[IngestRequest, bool]:
    request_id = new_id()
    values = {
        "id": request_id,
        "device_id": device_id,
        "idempotency_key": idempotency_key,
        "payload_sha256": payload_digest,
        "created_at": datetime.now(UTC),
    }
    dialect = session.get_bind().dialect.name

    if dialect == "postgresql":
        statement = (
            postgres_insert(IngestRequest)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_ingest_requests_device_idempotency")
            .returning(IngestRequest.id)
        )
        created_id = session.execute(statement).scalar_one_or_none()
    elif dialect == "sqlite":
        statement = (
            sqlite_insert(IngestRequest)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["device_id", "idempotency_key"])
            .returning(IngestRequest.id)
        )
        created_id = session.execute(statement).scalar_one_or_none()
    else:
        created_id = None
        try:
            with session.begin_nested():
                session.execute(insert(IngestRequest).values(**values))
            created_id = request_id
        except IntegrityError:
            pass

    if created_id is not None:
        created = session.get(IngestRequest, created_id)
        if created is None:
            raise RuntimeError("Created ingestion request could not be reloaded")
        return created, True

    existing = session.execute(
        select(IngestRequest).where(
            IngestRequest.device_id == device_id,
            IngestRequest.idempotency_key == idempotency_key,
        )
    ).scalar_one()
    return existing, False


def _measurement_values(
    *,
    device_id: str,
    ingest_request_id: str,
    readings: list[ReadingInput],
) -> list[dict[str, Any]]:
    received_at = datetime.now(UTC)
    return [
        {
            "id": new_id(),
            "device_id": device_id,
            "ingest_request_id": ingest_request_id,
            "sequence": reading.sequence,
            "observed_at": reading.observed_at,
            "received_at": received_at,
            "pm25_ug_m3": reading.pm25_ug_m3,
            "temperature_c": reading.temperature_c,
            "relative_humidity": reading.relative_humidity,
        }
        for reading in readings
    ]


def _insert_measurements(
    session: Session,
    *,
    device_id: str,
    ingest_request_id: str,
    readings: list[ReadingInput],
) -> int:
    values = _measurement_values(
        device_id=device_id,
        ingest_request_id=ingest_request_id,
        readings=readings,
    )
    dialect = session.get_bind().dialect.name

    if dialect == "postgresql":
        statement = (
            postgres_insert(Measurement)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_measurements_device_sequence")
            .returning(Measurement.id)
        )
        return len(session.execute(statement).scalars().all())
    if dialect == "sqlite":
        statement = (
            sqlite_insert(Measurement)
            .values(values)
            .on_conflict_do_nothing(index_elements=["device_id", "sequence"])
            .returning(Measurement.id)
        )
        return len(session.execute(statement).scalars().all())

    inserted = 0
    for value in values:
        try:
            with session.begin_nested():
                session.execute(insert(Measurement).values(**value))
            inserted += 1
        except IntegrityError:
            continue
    return inserted


@blueprint.post("/v1/devices/<device_id>/measurements:batch")
def ingest_measurements(device_id: str):
    started = time.perf_counter()
    raw_body = request.get_data(cache=True)
    idempotency_key = request.headers.get("Idempotency-Key", "")
    metrics = _metrics()

    if not IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise ApiError(
            400,
            "Invalid idempotency key",
            "Idempotency-Key must be 16-128 URL-safe characters",
            "invalid_idempotency_key",
        )

    session_factory = current_app.extensions["myaqi_session_factory"]
    try:
        with session_factory() as session, session.begin():
            device = session.get(Device, device_id)
            if device is None or not device.active:
                metrics.authentication_failures.inc()
                raise ApiError(
                    401,
                    "Authentication failed",
                    "Device credentials were rejected",
                    "authentication_failed",
                )

            secret = derive_device_secret(
                current_app.config["DEVICE_MASTER_KEY"],
                device.id,
                device.key_version,
            )
            try:
                verify_request_signature(
                    secret=secret,
                    timestamp=request.headers.get("X-Device-Timestamp"),
                    signature=request.headers.get("X-Device-Signature"),
                    method=request.method,
                    path=request.path,
                    body=raw_body,
                    max_clock_skew_seconds=current_app.config["AUTH_CLOCK_SKEW_SECONDS"],
                )
            except AuthenticationError as exc:
                metrics.authentication_failures.inc()
                raise ApiError(
                    401,
                    "Authentication failed",
                    "Device credentials were rejected",
                    "authentication_failed",
                ) from exc

            try:
                payload = request.get_json(silent=False)
                readings = parse_batch(
                    payload,
                    max_batch_size=current_app.config["MAX_BATCH_SIZE"],
                )
            except (BadRequest, PayloadError, ValueError) as exc:
                raise ApiError(
                    422,
                    "Invalid measurement batch",
                    str(exc),
                    "invalid_batch",
                ) from exc

            payload_digest = body_sha256(raw_body)
            ingest_request, created = _insert_ingest_request(
                session,
                device_id=device.id,
                idempotency_key=idempotency_key,
                payload_digest=payload_digest,
            )

            if not created:
                if ingest_request.payload_sha256 != payload_digest:
                    metrics.ingest_requests.labels(outcome="conflict").inc()
                    raise ApiError(
                        409,
                        "Idempotency conflict",
                        "The idempotency key was already used with a different payload",
                        "idempotency_conflict",
                    )
                if ingest_request.response_body is None:
                    raise ApiError(
                        409,
                        "Request still processing",
                        "The matching idempotent request has not completed",
                        "idempotency_in_progress",
                    )
                response_body = ingest_request.response_body
                response_status = ingest_request.response_status or 202
                replayed = True
            else:
                accepted = _insert_measurements(
                    session,
                    device_id=device.id,
                    ingest_request_id=ingest_request.id,
                    readings=readings,
                )
                duplicates = len(readings) - accepted
                response_body = {
                    "request_id": ingest_request.id,
                    "device_id": device.id,
                    "accepted": accepted,
                    "duplicates": duplicates,
                }
                response_status = 202
                ingest_request.response_body = response_body
                ingest_request.response_status = response_status
                session.add(
                    OutboxEvent(
                        event_type="measurements.ingested",
                        aggregate_type="ingest_request",
                        aggregate_id=ingest_request.id,
                        payload=response_body,
                    )
                )
                metrics.ingested_readings.labels(outcome="accepted").inc(accepted)
                metrics.ingested_readings.labels(outcome="duplicate").inc(duplicates)
                replayed = False

        metrics.ingest_requests.labels(outcome="replayed" if replayed else "accepted").inc()
        response = jsonify(response_body)
        response.status_code = response_status
        if replayed:
            response.headers["Idempotent-Replayed"] = "true"
        return response
    finally:
        metrics.ingest_latency.observe(time.perf_counter() - started)
