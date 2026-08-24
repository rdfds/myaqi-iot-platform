from __future__ import annotations

import io
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from soak.collect_serial import parse_serial_line, write_record  # noqa: E402


def test_parse_serial_line_accepts_complete_diagnostic() -> None:
    diagnostic = {
        "firmware_version": "2026.08.24+ops1",
        "next_sequence": 42,
        "pending_readings": 3,
        "dropped_readings": 0,
        "upload_attempts": 40,
        "upload_failures": 2,
        "last_http_status": 202,
        "last_acknowledged_sequence": 38,
    }

    parsed = parse_serial_line("MYAQI_DIAGNOSTIC " + json.dumps(diagnostic))

    assert parsed == {"kind": "diagnostic", "diagnostic": diagnostic}


def test_parse_serial_line_ignores_raw_and_partial_records() -> None:
    assert parse_serial_line("Wi-Fi password: do-not-capture") is None
    assert parse_serial_line('MYAQI_DIAGNOSTIC {"pending_readings":2}') is None
    assert parse_serial_line("MYAQI_DIAGNOSTIC not-json") is None


def test_write_record_is_jsonl_and_flushes() -> None:
    handle = io.StringIO()
    write_record(handle, {"kind": "diagnostic", "value": 2})
    assert json.loads(handle.getvalue()) == {"kind": "diagnostic", "value": 2}
    assert handle.getvalue().endswith("\n")
