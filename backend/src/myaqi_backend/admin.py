from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from myaqi_backend.auth import derive_device_secret, encode_device_secret
from myaqi_backend.config import Settings
from myaqi_backend.database import make_engine, make_session_factory
from myaqi_backend.models import Device, Measurement, OutboxEvent


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _missing_ranges(sequences: list[int], start: int, end: int) -> list[list[int]]:
    ranges: list[list[int]] = []
    expected = start
    for sequence in sequences:
        if sequence > expected:
            ranges.append([expected, sequence - 1])
        expected = sequence + 1
    if expected <= end:
        ranges.append([expected, end])
    return ranges


def provision_device(device_id: str, display_name: str, *, settings: Settings) -> dict[str, object]:
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session, session.begin():
            existing = session.get(Device, device_id)
            if existing is None:
                device = Device(id=device_id, display_name=display_name)
                session.add(device)
            else:
                device = existing
                device.display_name = display_name
                device.active = True

        secret = derive_device_secret(settings.device_master_key, device.id, device.key_version)
        return {
            "device_id": device.id,
            "display_name": device.display_name,
            "key_version": device.key_version,
            "device_secret": encode_device_secret(secret),
        }
    finally:
        engine.dispose()


def seed_benchmark_devices(
    *,
    count: int,
    prefix: str,
    output: Path,
    settings: Settings,
) -> dict[str, object]:
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    device_ids = [f"{prefix}-{index:04d}" for index in range(1, count + 1)]
    try:
        with factory() as session, session.begin():
            existing = set(
                session.execute(select(Device.id).where(Device.id.in_(device_ids))).scalars()
            )
            for device_id in device_ids:
                if device_id not in existing:
                    session.add(Device(id=device_id, display_name=f"Benchmark device {device_id}"))

        devices = [
            {
                "device_id": device_id,
                "device_secret": encode_device_secret(
                    derive_device_secret(settings.device_master_key, device_id)
                ),
            }
            for device_id in device_ids
        ]
        output.write_text(json.dumps({"devices": devices}, indent=2) + "\n", encoding="utf-8")
        return {"devices": count, "output": str(output)}
    finally:
        engine.dispose()


def inspect_device(device_id: str, *, settings: Settings) -> dict[str, object]:
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            device = session.get(Device, device_id)
            if device is None:
                raise ValueError(f"Unknown device: {device_id}")
            measurement_summary = session.execute(
                select(
                    func.count(Measurement.id),
                    func.min(Measurement.sequence),
                    func.max(Measurement.sequence),
                ).where(Measurement.device_id == device_id)
            ).one()
            outbox_counts = {
                status: count
                for status, count in session.execute(
                    select(OutboxEvent.status, func.count(OutboxEvent.id))
                    .where(
                        OutboxEvent.aggregate_id.in_(
                            select(Measurement.ingest_request_id).where(
                                Measurement.device_id == device_id
                            )
                        )
                    )
                    .group_by(OutboxEvent.status)
                )
            }
            count, first_sequence, last_sequence = measurement_summary
            observed_span = (
                last_sequence - first_sequence + 1
                if first_sequence is not None and last_sequence is not None
                else 0
            )
            return {
                "device_id": device.id,
                "display_name": device.display_name,
                "active": device.active,
                "key_version": device.key_version,
                "last_seen_at": _isoformat(device.last_seen_at),
                "last_firmware_version": device.last_firmware_version,
                "reported_last_sequence": device.last_sequence,
                "persisted_measurements": count,
                "first_persisted_sequence": first_sequence,
                "last_persisted_sequence": last_sequence,
                "missing_within_persisted_span": observed_span - count,
                "outbox": outbox_counts,
            }
    finally:
        engine.dispose()


def verify_sequence_range(
    device_id: str,
    *,
    start: int,
    end: int,
    settings: Settings,
) -> dict[str, object]:
    if start < 1 or end < start or end - start + 1 > 1_000_000:
        raise ValueError("Sequence range must contain 1-1,000,000 positive values")
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            if session.get(Device, device_id) is None:
                raise ValueError(f"Unknown device: {device_id}")
            sequences = list(
                session.execute(
                    select(Measurement.sequence)
                    .where(
                        Measurement.device_id == device_id,
                        Measurement.sequence.between(start, end),
                    )
                    .order_by(Measurement.sequence)
                ).scalars()
            )
            missing = _missing_ranges(sequences, start, end)
            return {
                "device_id": device_id,
                "start": start,
                "end": end,
                "received": len(sequences),
                "missing": end - start + 1 - len(sequences),
                "missing_ranges": missing,
                "complete": not missing,
            }
    finally:
        engine.dispose()


def list_dead_events(*, limit: int, settings: Settings) -> dict[str, object]:
    if limit < 1 or limit > 1000:
        raise ValueError("Limit must be between 1 and 1000")
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            events = list(
                session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.status == "dead")
                    .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id)
                    .limit(limit)
                ).scalars()
            )
            return {
                "events": [
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "attempts": event.attempts,
                        "last_error": event.last_error,
                        "created_at": _isoformat(event.created_at),
                    }
                    for event in events
                ]
            }
    finally:
        engine.dispose()


def replay_event(event_id: str, *, settings: Settings) -> dict[str, object]:
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    replayed_at = datetime.now(UTC)
    try:
        with factory() as session, session.begin():
            event = session.get(OutboxEvent, event_id, with_for_update=True)
            if event is None:
                raise ValueError(f"Unknown event: {event_id}")
            if event.status != "dead":
                raise ValueError(f"Event {event_id} is {event.status}, not dead")
            event.status = "pending"
            event.available_at = replayed_at
            event.locked_at = None
            event.locked_by = None
            return {
                "event_id": event.id,
                "status": event.status,
                "attempts_retained": event.attempts,
                "replayed_at": replayed_at.isoformat(),
            }
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administer myAQI reference devices")
    subparsers = parser.add_subparsers(dest="command", required=True)

    provision = subparsers.add_parser("provision-device")
    provision.add_argument("device_id")
    provision.add_argument("--name", required=True)

    seed = subparsers.add_parser("seed-benchmark-devices")
    seed.add_argument("--count", type=int, default=250)
    seed.add_argument("--prefix", default="benchmark")
    seed.add_argument("--output", type=Path, default=Path("benchmark-devices.json"))

    inspect = subparsers.add_parser("inspect-device")
    inspect.add_argument("device_id")

    verify = subparsers.add_parser("verify-sequence-range")
    verify.add_argument("device_id")
    verify.add_argument("--start", type=int, required=True)
    verify.add_argument("--end", type=int, required=True)

    dead = subparsers.add_parser("list-dead-events")
    dead.add_argument("--limit", type=int, default=100)

    replay = subparsers.add_parser("replay-event")
    replay.add_argument("event_id")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    if args.command == "provision-device":
        result = provision_device(args.device_id, args.name, settings=settings)
    elif args.command == "seed-benchmark-devices":
        if args.count < 1 or args.count > 10_000:
            raise SystemExit("--count must be between 1 and 10000")
        result = seed_benchmark_devices(
            count=args.count,
            prefix=args.prefix,
            output=args.output,
            settings=settings,
        )
    elif args.command == "inspect-device":
        result = inspect_device(args.device_id, settings=settings)
    elif args.command == "verify-sequence-range":
        result = verify_sequence_range(
            args.device_id,
            start=args.start,
            end=args.end,
            settings=settings,
        )
    elif args.command == "list-dead-events":
        result = list_dead_events(limit=args.limit, settings=settings)
    else:
        result = replay_event(args.event_id, settings=settings)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
