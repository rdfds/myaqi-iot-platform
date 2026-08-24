from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from soak.verify_results import build_report  # noqa: E402


def test_build_report_requires_completed_faults_and_sequence_audit() -> None:
    manifest = {
        "run_id": "run-1",
        "scenario": "test",
        "device_id": "soak-001",
        "revision": "abc123",
        "started_at": "2026-08-24T00:00:00+00:00",
        "ended_at": "2026-08-24T01:00:00+00:00",
        "status": "completed",
        "elapsed_seconds": 3600,
        "run_duration_seconds": 3600,
        "expected_start_sequence": 10,
        "expected_checkpoints": 1,
    }
    baseline = {
        "firmware_version": "2026.08.24+ops1",
        "pending_readings": 0,
        "dropped_readings": 2,
        "upload_attempts": 8,
        "upload_failures": 1,
        "last_acknowledged_sequence": 9,
    }
    final = {
        **baseline,
        "pending_readings": 0,
        "upload_attempts": 18,
        "upload_failures": 3,
        "last_acknowledged_sequence": 19,
    }
    serial_records = [
        {"kind": "serial_connected"},
        {"kind": "diagnostic", "diagnostic": baseline},
        {"kind": "diagnostic", "diagnostic": final},
    ]
    operator_records = [{"kind": "checkpoint_confirmed"}]
    backend_report = {
        "device_id": "soak-001",
        "start": 10,
        "end": 19,
        "received": 10,
        "missing": 0,
        "complete": True,
    }

    report = build_report(manifest, serial_records, operator_records, backend_report)

    assert report["passed"] is True
    assert report["metrics"]["new_upload_failures"] == 2
    assert report["metrics"]["new_dropped_readings"] == 0


def test_build_report_fails_when_the_final_queue_is_not_drained() -> None:
    manifest = {
        "status": "completed",
        "elapsed_seconds": 60,
        "run_duration_seconds": 60,
        "expected_start_sequence": 1,
        "expected_checkpoints": 0,
        "device_id": "soak-001",
    }
    diagnostic = {
        "firmware_version": "v1",
        "pending_readings": 1,
        "dropped_readings": 0,
        "upload_attempts": 1,
        "upload_failures": 0,
        "last_acknowledged_sequence": None,
    }
    backend_report = {
        "device_id": "soak-001",
        "start": 1,
        "received": 0,
        "missing": 1,
        "complete": False,
    }

    report = build_report(
        manifest,
        [
            {"kind": "diagnostic", "diagnostic": diagnostic},
            {"kind": "diagnostic", "diagnostic": diagnostic},
        ],
        [],
        backend_report,
    )

    assert report["passed"] is False
    assert report["checks"]["device_queue_drained"] is False
    assert report["checks"]["backend_sequence_range_complete"] is False
