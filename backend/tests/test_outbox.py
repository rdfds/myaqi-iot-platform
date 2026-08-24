from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import myaqi_backend.outbox as outbox_module
from myaqi_backend.config import Settings
from myaqi_backend.models import OutboxEvent
from myaqi_backend.outbox import (
    ClaimedEvent,
    SnsPublisher,
    build_publisher,
    claim_events,
    mark_failed,
    mark_published,
    outbox_health,
    process_once,
)


def add_event(app) -> str:
    factory = app.extensions["myaqi_session_factory"]
    with factory() as session, session.begin():
        event = OutboxEvent(
            event_type="measurements.ingested",
            aggregate_type="ingest_request",
            aggregate_id="request-1",
            payload={"accepted": 2},
        )
        session.add(event)
        session.flush()
        return event.id


def test_claim_is_exclusive_and_publish_requires_lock_owner(app) -> None:
    event_id = add_event(app)
    factory = app.extensions["myaqi_session_factory"]

    first = claim_events(
        factory,
        worker_id="worker-a",
        batch_size=10,
        lock_timeout_seconds=60,
    )
    second = claim_events(
        factory,
        worker_id="worker-b",
        batch_size=10,
        lock_timeout_seconds=60,
    )

    assert [event.id for event in first] == [event_id]
    assert second == []
    assert mark_published(factory, event_id=event_id, worker_id="worker-b") is False
    assert mark_published(factory, event_id=event_id, worker_id="worker-a") is True

    with factory() as session:
        event = session.get(OutboxEvent, event_id)
        assert event.status == "published"
        assert event.published_at is not None


def test_failed_event_retries_then_moves_to_dead_letter_state(app) -> None:
    event_id = add_event(app)
    factory = app.extensions["myaqi_session_factory"]
    started = datetime.now(UTC)

    for attempt in range(1, 3):
        claimed = claim_events(
            factory,
            worker_id="worker-a",
            batch_size=1,
            lock_timeout_seconds=60,
            now=started + timedelta(minutes=attempt),
        )
        assert [event.id for event in claimed] == [event_id]
        assert mark_failed(
            factory,
            event_id=event_id,
            worker_id="worker-a",
            error=RuntimeError("provider unavailable"),
            max_attempts=2,
            now=started + timedelta(minutes=attempt),
        )

    with factory() as session:
        event = session.get(OutboxEvent, event_id)
        assert event.status == "dead"
        assert event.attempts == 2
        assert event.last_error == "provider unavailable"


def test_process_once_publishes_claimed_event(app) -> None:
    event_id = add_event(app)
    factory = app.extensions["myaqi_session_factory"]
    published: list[str] = []

    class RecordingPublisher:
        def publish(self, event: ClaimedEvent) -> None:
            published.append(event.id)

    processed = process_once(
        factory,
        publisher=RecordingPublisher(),
        worker_id="worker-a",
        batch_size=10,
        lock_timeout_seconds=60,
        max_attempts=3,
    )

    assert processed == 1
    assert published == [event_id]
    with factory() as session:
        assert session.get(OutboxEvent, event_id).status == "published"


def test_process_once_schedules_failed_publish(app) -> None:
    event_id = add_event(app)
    factory = app.extensions["myaqi_session_factory"]

    class FailingPublisher:
        def publish(self, event: ClaimedEvent) -> None:
            raise RuntimeError(f"cannot publish {event.id}")

    processed = process_once(
        factory,
        publisher=FailingPublisher(),
        worker_id="worker-a",
        batch_size=10,
        lock_timeout_seconds=60,
        max_attempts=3,
    )

    assert processed == 1
    with factory() as session:
        event = session.get(OutboxEvent, event_id)
        assert event.status == "pending"
        assert event.attempts == 1
        assert event.locked_by is None


def test_outbox_health_reports_backlog_age_and_dead_events(app) -> None:
    event_id = add_event(app)
    factory = app.extensions["myaqi_session_factory"]
    checked_at = datetime.now(UTC) + timedelta(seconds=30)

    initial = outbox_health(factory, now=checked_at)
    assert initial["pending"] == 1
    assert initial["processing"] == 0
    assert initial["dead"] == 0
    assert initial["oldest_pending_seconds"] >= 29

    claim_events(
        factory,
        worker_id="worker-a",
        batch_size=1,
        lock_timeout_seconds=60,
    )
    mark_failed(
        factory,
        event_id=event_id,
        worker_id="worker-a",
        error=RuntimeError("permanent failure"),
        max_attempts=1,
    )
    failed = outbox_health(factory, now=checked_at)
    assert failed["pending"] == 0
    assert failed["dead"] == 1
    assert failed["oldest_pending_seconds"] == 0


def test_sns_publisher_preserves_event_identity_and_type() -> None:
    calls: list[dict[str, object]] = []

    class RecordingSnsClient:
        def publish(self, **kwargs) -> object:
            calls.append(kwargs)
            return {"MessageId": "message-1"}

    publisher = SnsPublisher(
        "arn:aws:sns:us-east-1:123456789012:myaqi-events",
        client=RecordingSnsClient(),
    )
    publisher.publish(
        ClaimedEvent(
            id="event-1",
            event_type="measurements.ingested",
            payload={"accepted": 2},
        )
    )

    assert calls[0]["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:myaqi-events"
    assert json.loads(str(calls[0]["Message"])) == {
        "event_id": "event-1",
        "event_type": "measurements.ingested",
        "payload": {"accepted": 2},
    }
    assert calls[0]["MessageAttributes"] == {
        "event_type": {
            "DataType": "String",
            "StringValue": "measurements.ingested",
        }
    }


def test_publisher_selection_uses_sns_only_when_configured(monkeypatch) -> None:
    local_settings = replace(Settings.from_env(), outbox_sns_topic_arn=None)
    assert type(build_publisher(local_settings)).__name__ == "LoggingPublisher"

    monkeypatch.setattr(
        outbox_module,
        "SnsPublisher",
        lambda topic_arn: ("sns", topic_arn),
    )
    cloud_settings = replace(
        local_settings,
        outbox_sns_topic_arn="arn:aws:sns:us-east-1:123456789012:myaqi-events",
    )
    assert build_publisher(cloud_settings) == (
        "sns",
        "arn:aws:sns:us-east-1:123456789012:myaqi-events",
    )
