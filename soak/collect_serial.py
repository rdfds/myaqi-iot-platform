from __future__ import annotations

import argparse
import json
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import TextIO

import serial

DIAGNOSTIC_PREFIX = "MYAQI_DIAGNOSTIC "
REQUIRED_DIAGNOSTIC_FIELDS = {
    "firmware_version",
    "next_sequence",
    "pending_readings",
    "dropped_readings",
    "upload_attempts",
    "upload_failures",
    "last_http_status",
    "last_acknowledged_sequence",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def parse_serial_line(line: str) -> dict[str, object] | None:
    if not line.startswith(DIAGNOSTIC_PREFIX):
        return None
    try:
        payload = json.loads(line[len(DIAGNOSTIC_PREFIX) :])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not REQUIRED_DIAGNOSTIC_FIELDS.issubset(payload):
        return None
    return {"kind": "diagnostic", "diagnostic": payload}


def write_record(handle: TextIO, record: dict[str, object]) -> None:
    handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    handle.flush()


def capture(
    *,
    port: str,
    baud: int,
    output: Path,
    stop_requested: Event,
    include_raw: bool = False,
    retry_seconds: float = 2.0,
) -> None:
    started = time.monotonic()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        while not stop_requested.is_set():
            try:
                with serial.Serial(port, baudrate=baud, timeout=1) as device:
                    write_record(
                        handle,
                        {
                            "kind": "serial_connected",
                            "captured_at": utc_now(),
                            "elapsed_seconds": round(time.monotonic() - started, 3),
                            "port": port,
                        },
                    )
                    while not stop_requested.is_set():
                        raw = device.readline()
                        if not raw:
                            continue
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        parsed = parse_serial_line(line)
                        if parsed is None and not include_raw:
                            continue
                        record = parsed or {"kind": "raw", "line": line}
                        write_record(
                            handle,
                            {
                                **record,
                                "captured_at": utc_now(),
                                "elapsed_seconds": round(time.monotonic() - started, 3),
                            },
                        )
            except (OSError, serial.SerialException) as error:
                write_record(
                    handle,
                    {
                        "kind": "serial_disconnected",
                        "captured_at": utc_now(),
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "error": str(error)[:240],
                    },
                )
                stop_requested.wait(max(0.1, retry_seconds))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture structured myAQI diagnostics across board disconnects"
    )
    parser.add_argument("--port", required=True, help="Serial device, e.g. /dev/cu.usbmodem101")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Also retain unstructured serial lines; review them for sensitive data",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    stop_requested = Event()

    def request_stop(_signum, _frame) -> None:
        stop_requested.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    capture(
        port=args.port,
        baud=args.baud,
        output=args.output,
        stop_requested=stop_requested,
        include_raw=args.include_raw,
    )


if __name__ == "__main__":
    main()
