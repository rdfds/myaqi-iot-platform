from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Protocol

from sqlalchemy import and_, func, or_, select

from myaqi_backend.config import Settings
from myaqi_backend.database import SessionFactory, make_engine, make_session_factory
from myaqi_backend.logging_config import configure_logging
from myaqi_backend.models import OutboxEvent

logger = logging.getLogger("myaqi.outbox")


@dataclass(frozen=True)
class ClaimedEvent:
    id: str
    event_type: str
    payload: dict[str, object]


class Publisher(Protocol):
    def publish(self, event: ClaimedEvent) -> None: ...


class LoggingPublisher:
    """Reference publisher that exposes the handoff without hiding a queue dependency."""

    def publish(self, event: ClaimedEvent) -> None:
        logger.info(
            "outbox_event_published",
            extra={"event_id": event.id, "event_type": event.event_type},
        )


def outbox_health(
    factory: SessionFactory,
    *,
    now: datetime | None = None,
) -> dict[str, int | float]:
    checked_at = now or datetime.now(UTC)
    with factory() as session:
        counts = {
            status: count
            for status, count in session.execute(
                select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(
                    OutboxEvent.status
                )
            )
        }
        oldest_pending = session.scalar(
            select(func.min(OutboxEvent.created_at)).where(
                OutboxEvent.status.in_(("pending", "processing"))
            )
        )
    if oldest_pending is not None and oldest_pending.tzinfo is None:
        oldest_pending = oldest_pending.replace(tzinfo=UTC)
    oldest_seconds = (
        max(0.0, (checked_at - oldest_pending).total_seconds())
        if oldest_pending is not None
        else 0.0
    )
    return {
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "dead": counts.get("dead", 0),
        "oldest_pending_seconds": round(oldest_seconds, 3),
    }


def claim_events(
    factory: SessionFactory,
    *,
    worker_id: str,
    batch_size: int,
    lock_timeout_seconds: int,
    now: datetime | None = None,
) -> list[ClaimedEvent]:
    claimed_at = now or datetime.now(UTC)
    stale_before = claimed_at - timedelta(seconds=lock_timeout_seconds)

    with factory() as session, session.begin():
        statement = (
            select(OutboxEvent)
            .where(
                or_(
                    and_(
                        OutboxEvent.status == "pending",
                        OutboxEvent.available_at <= claimed_at,
                    ),
                    and_(
                        OutboxEvent.status == "processing",
                        OutboxEvent.locked_at <= stale_before,
                    ),
                )
            )
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        events = list(session.execute(statement).scalars())
        for event in events:
            event.status = "processing"
            event.locked_at = claimed_at
            event.locked_by = worker_id

        return [
            ClaimedEvent(id=event.id, event_type=event.event_type, payload=event.payload)
            for event in events
        ]


def mark_published(
    factory: SessionFactory,
    *,
    event_id: str,
    worker_id: str,
    now: datetime | None = None,
) -> bool:
    published_at = now or datetime.now(UTC)
    with factory() as session, session.begin():
        event = session.get(OutboxEvent, event_id, with_for_update=True)
        if event is None or event.status != "processing" or event.locked_by != worker_id:
            return False
        event.status = "published"
        event.published_at = published_at
        event.locked_at = None
        event.locked_by = None
        event.last_error = None
        return True


def mark_failed(
    factory: SessionFactory,
    *,
    event_id: str,
    worker_id: str,
    error: Exception,
    max_attempts: int,
    now: datetime | None = None,
) -> bool:
    failed_at = now or datetime.now(UTC)
    with factory() as session, session.begin():
        event = session.get(OutboxEvent, event_id, with_for_update=True)
        if event is None or event.status != "processing" or event.locked_by != worker_id:
            return False

        event.attempts += 1
        event.last_error = str(error)[:2000]
        event.locked_at = None
        event.locked_by = None
        if event.attempts >= max_attempts:
            event.status = "dead"
        else:
            event.status = "pending"
            backoff_seconds = min(300, 2 ** min(event.attempts, 8))
            event.available_at = failed_at + timedelta(seconds=backoff_seconds)
        return True


def process_once(
    factory: SessionFactory,
    *,
    publisher: Publisher,
    worker_id: str,
    batch_size: int,
    lock_timeout_seconds: int,
    max_attempts: int,
) -> int:
    events = claim_events(
        factory,
        worker_id=worker_id,
        batch_size=batch_size,
        lock_timeout_seconds=lock_timeout_seconds,
    )
    for event in events:
        try:
            publisher.publish(event)
        except Exception as exc:
            logger.exception(
                "outbox_publish_failed",
                extra={"event_id": event.id, "worker_id": worker_id},
            )
            mark_failed(
                factory,
                event_id=event.id,
                worker_id=worker_id,
                error=exc,
                max_attempts=max_attempts,
            )
        else:
            mark_published(factory, event_id=event.id, worker_id=worker_id)
    return len(events)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process myAQI transactional outbox events")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    factory = make_session_factory(make_engine(settings.database_url))
    worker_id = os.getenv("WORKER_ID", f"{socket.gethostname()}-{os.getpid()}")
    publisher = LoggingPublisher()
    stop_requested = Event()

    def request_stop(signum, _frame) -> None:
        logger.info(
            "worker_stop_requested",
            extra={"worker_id": worker_id, "signal": signum},
        )
        stop_requested.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    next_health_log = 0.0

    while not stop_requested.is_set():
        count = process_once(
            factory,
            publisher=publisher,
            worker_id=worker_id,
            batch_size=settings.outbox_batch_size,
            lock_timeout_seconds=settings.outbox_lock_timeout_seconds,
            max_attempts=settings.outbox_max_attempts,
        )
        if args.once:
            print(
                json.dumps(
                    {
                        "worker_id": worker_id,
                        "processed": count,
                        "health": outbox_health(factory),
                    }
                )
            )
            return
        current_time = time.monotonic()
        if current_time >= next_health_log:
            logger.info(
                "outbox_health",
                extra={"worker_id": worker_id, **outbox_health(factory)},
            )
            next_health_log = current_time + max(
                5,
                settings.outbox_health_interval_seconds,
            )
        if count == 0:
            stop_requested.wait(max(0.05, args.poll_seconds))
    logger.info("worker_stopped", extra={"worker_id": worker_id})


if __name__ == "__main__":
    main()
