from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from myaqi_backend.admin import (
    build_parser,
    inspect_device,
    list_dead_events,
    provision_device,
    replay_event,
    seed_benchmark_devices,
    verify_sequence_range,
)
from myaqi_backend.config import Settings
from myaqi_backend.database import Base, make_engine, make_session_factory
from myaqi_backend.models import Device, IngestRequest, Measurement, OutboxEvent


def test_admin_provisions_and_seeds_devices(tmp_path) -> None:
    database_path = tmp_path / "admin.db"
    settings = replace(
        Settings.from_env(),
        database_url=f"sqlite+pysqlite:///{database_path}",
        device_master_key="admin-test-master-key-with-32-characters",
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    first = provision_device("school-101", "Room 101", settings=settings)
    second = provision_device("school-101", "Updated room", settings=settings)

    assert first["device_secret"] == second["device_secret"]
    assert second["display_name"] == "Updated room"

    output = tmp_path / "devices.json"
    result = seed_benchmark_devices(
        count=3,
        prefix="load",
        output=output,
        settings=settings,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result == {"devices": 3, "output": str(output)}
    assert [device["device_id"] for device in payload["devices"]] == [
        "load-0001",
        "load-0002",
        "load-0003",
    ]
    factory = make_session_factory(engine)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Device)) == 4
    engine.dispose()


def test_admin_parser_exposes_operational_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["inspect-device", "school-001"]).command == "inspect-device"
    verify = parser.parse_args(
        ["verify-sequence-range", "school-001", "--start", "10", "--end", "20"]
    )
    assert (verify.start, verify.end) == (10, 20)
    assert parser.parse_args(["list-dead-events"]).limit == 100
    assert parser.parse_args(["replay-event", "event-1"]).event_id == "event-1"


def test_admin_inspects_sequences_and_replays_dead_events(tmp_path) -> None:
    database_path = tmp_path / "operations.db"
    settings = replace(
        Settings.from_env(),
        database_url=f"sqlite+pysqlite:///{database_path}",
        device_master_key="admin-test-master-key-with-32-characters",
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as session, session.begin():
        device = Device(
            id="school-202",
            display_name="Room 202",
            last_seen_at=None,
            last_firmware_version="2026.08.24+2",
            last_sequence=14,
        )
        request = IngestRequest(
            device_id=device.id,
            idempotency_key="admin-test-request-0001",
            payload_sha256="a" * 64,
            response_status=202,
            response_body={"accepted": 2},
        )
        session.add_all([device, request])
        session.flush()
        session.add_all(
            [
                Measurement(
                    device_id=device.id,
                    ingest_request_id=request.id,
                    sequence=10,
                    observed_at=datetime.now(UTC),
                    pm25_ug_m3=10.0,
                ),
                Measurement(
                    device_id=device.id,
                    ingest_request_id=request.id,
                    sequence=12,
                    observed_at=datetime.now(UTC),
                    pm25_ug_m3=12.0,
                ),
                OutboxEvent(
                    event_type="measurements.ingested",
                    aggregate_type="ingest_request",
                    aggregate_id=request.id,
                    payload={"accepted": 2},
                    status="dead",
                    attempts=8,
                    last_error="downstream timeout",
                ),
            ]
        )
    engine.dispose()

    inspected = inspect_device("school-202", settings=settings)
    assert inspected["persisted_measurements"] == 2
    assert inspected["missing_within_persisted_span"] == 1
    assert inspected["last_firmware_version"] == "2026.08.24+2"

    verified = verify_sequence_range("school-202", start=10, end=14, settings=settings)
    assert verified["received"] == 2
    assert verified["missing"] == 3
    assert verified["missing_ranges"] == [[11, 11], [13, 14]]
    assert verified["complete"] is False

    dead = list_dead_events(limit=10, settings=settings)
    assert len(dead["events"]) == 1
    replayed = replay_event(dead["events"][0]["id"], settings=settings)
    assert replayed["status"] == "pending"
    assert replayed["attempts_retained"] == 8
    assert list_dead_events(limit=10, settings=settings) == {"events": []}

    with pytest.raises(ValueError, match="Unknown device"):
        inspect_device("unknown-device", settings=settings)
    with pytest.raises(ValueError, match="Sequence range"):
        verify_sequence_range("school-202", start=0, end=10, settings=settings)
    with pytest.raises(ValueError, match="Unknown device"):
        verify_sequence_range("unknown-device", start=1, end=10, settings=settings)
    with pytest.raises(ValueError, match="Limit"):
        list_dead_events(limit=0, settings=settings)
    with pytest.raises(ValueError, match="Unknown event"):
        replay_event("unknown-event", settings=settings)
    with pytest.raises(ValueError, match="not dead"):
        replay_event(dead["events"][0]["id"], settings=settings)
