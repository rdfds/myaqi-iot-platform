from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON on {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"Expected object on {path}:{line_number}")
        records.append(value)
    return records


def build_report(
    manifest: dict[str, object],
    serial_records: list[dict[str, object]],
    operator_records: list[dict[str, object]],
    backend_report: dict[str, object],
) -> dict[str, object]:
    diagnostics = [
        record["diagnostic"]
        for record in serial_records
        if record.get("kind") == "diagnostic" and isinstance(record.get("diagnostic"), dict)
    ]
    if len(diagnostics) < 2:
        raise ValueError("At least two structured diagnostics are required")
    first = diagnostics[0]
    last = diagnostics[-1]
    checkpoint_count = sum(
        record.get("kind") == "checkpoint_confirmed" for record in operator_records
    )
    expected_checkpoints = int(manifest.get("expected_checkpoints", 0))
    checks = {
        "run_completed": manifest.get("status") == "completed",
        "planned_duration_completed": float(manifest.get("elapsed_seconds", 0))
        >= int(manifest["run_duration_seconds"]),
        "all_checkpoints_confirmed": checkpoint_count == expected_checkpoints,
        "no_new_dropped_readings": int(last["dropped_readings"])
        == int(first["dropped_readings"]),
        "device_queue_drained": int(last["pending_readings"]) == 0,
        "backend_sequence_range_complete": backend_report.get("complete") is True
        and int(backend_report.get("missing", -1)) == 0,
        "backend_device_matches": backend_report.get("device_id") == manifest.get("device_id"),
        "backend_range_starts_as_planned": int(backend_report.get("start", -1))
        == int(manifest["expected_start_sequence"]),
        "firmware_revision_stable": len(
            {str(diagnostic["firmware_version"]) for diagnostic in diagnostics}
        )
        == 1,
    }
    metrics = {
        "diagnostic_records": len(diagnostics),
        "serial_reconnects": sum(
            record.get("kind") == "serial_connected" for record in serial_records
        ),
        "confirmed_checkpoints": checkpoint_count,
        "new_upload_attempts": int(last["upload_attempts"]) - int(first["upload_attempts"]),
        "new_upload_failures": int(last["upload_failures"]) - int(first["upload_failures"]),
        "maximum_pending_readings": max(
            int(diagnostic["pending_readings"]) for diagnostic in diagnostics
        ),
        "new_dropped_readings": int(last["dropped_readings"])
        - int(first["dropped_readings"]),
        "final_acknowledged_sequence": last["last_acknowledged_sequence"],
        "backend_received": backend_report.get("received"),
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": manifest.get("run_id"),
        "scenario": manifest.get("scenario"),
        "device_id": manifest.get("device_id"),
        "revision": manifest.get("revision"),
        "started_at": manifest.get("started_at"),
        "ended_at": manifest.get("ended_at"),
        "metrics": metrics,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a myAQI hardware soak evidence bundle")
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--backend-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(
        json.loads((args.run_directory / "manifest.json").read_text(encoding="utf-8")),
        load_jsonl(args.run_directory / "serial.jsonl"),
        load_jsonl(args.run_directory / "operator-events.jsonl"),
        json.loads(args.backend_report.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
