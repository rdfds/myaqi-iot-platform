from __future__ import annotations

import json
from dataclasses import replace

from sqlalchemy import func, select

from myaqi_backend.admin import provision_device, seed_benchmark_devices
from myaqi_backend.config import Settings
from myaqi_backend.database import Base, make_engine, make_session_factory
from myaqi_backend.models import Device


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
