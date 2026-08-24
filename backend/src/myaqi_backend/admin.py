from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from myaqi_backend.auth import derive_device_secret, encode_device_secret
from myaqi_backend.config import Settings
from myaqi_backend.database import make_engine, make_session_factory
from myaqi_backend.models import Device


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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    if args.command == "provision-device":
        result = provision_device(args.device_id, args.name, settings=settings)
    else:
        if args.count < 1 or args.count > 10_000:
            raise SystemExit("--count must be between 1 and 10000")
        result = seed_benchmark_devices(
            count=args.count,
            prefix=args.prefix,
            output=args.output,
            settings=settings,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
