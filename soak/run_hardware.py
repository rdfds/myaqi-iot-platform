from __future__ import annotations

import argparse
import json
import signal
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread

import yaml

from soak.collect_serial import capture, write_record


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_scenario(path: Path, name: str) -> dict[str, object]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenarios = document.get("scenarios", {}) if isinstance(document, dict) else {}
    scenario = scenarios.get(name) if isinstance(scenarios, dict) else None
    if not isinstance(scenario, dict):
        raise ValueError(f"Unknown soak scenario: {name}")
    return scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a supervised myAQI hardware soak test")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--revision", required=True, help="Deployed Git commit SHA")
    parser.add_argument("--expected-start-sequence", type=int, required=True)
    parser.add_argument("--scenario", default="seven-day-resilience")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path(__file__).with_name("scenarios.yaml"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--duration-seconds",
        type=int,
        help="Shorter duration for harness validation; recorded in the manifest",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.expected_start_sequence < 1:
        raise SystemExit("--expected-start-sequence must be positive")
    scenario = load_scenario(args.scenarios, args.scenario)
    planned_duration = int(scenario["duration_seconds"])
    duration = args.duration_seconds or planned_duration
    if duration < 1:
        raise SystemExit("duration must be positive")

    args.output.mkdir(parents=True, exist_ok=False)
    manifest_path = args.output / "manifest.json"
    serial_path = args.output / "serial.jsonl"
    operator_path = args.output / "operator-events.jsonl"
    manifest: dict[str, object] = {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        "scenario": args.scenario,
        "scenario_description": scenario.get("description"),
        "device_id": args.device_id,
        "revision": args.revision,
        "serial_port": args.port,
        "baud": args.baud,
        "expected_start_sequence": args.expected_start_sequence,
        "planned_duration_seconds": planned_duration,
        "run_duration_seconds": duration,
        "started_at": utc_now(),
        "status": "running",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    stop_requested = Event()

    def request_stop(_signum, _frame) -> None:
        stop_requested.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    collector = Thread(
        target=capture,
        kwargs={
            "port": args.port,
            "baud": args.baud,
            "output": serial_path,
            "stop_requested": stop_requested,
        },
        daemon=True,
    )
    collector.start()
    started = time.monotonic()
    checkpoints = [
        checkpoint
        for checkpoint in scenario.get("checkpoints", [])
        if int(checkpoint["at_seconds"]) <= duration
    ]

    try:
        with operator_path.open("a", encoding="utf-8") as operator_log:
            for index, checkpoint in enumerate(checkpoints, start=1):
                target = started + int(checkpoint["at_seconds"])
                while not stop_requested.is_set() and time.monotonic() < target:
                    stop_requested.wait(min(30, target - time.monotonic()))
                if stop_requested.is_set():
                    break
                action = str(checkpoint["action"])
                print(f"Checkpoint {index}/{len(checkpoints)}: {action}")
                input("Complete the action, retain any external evidence, then press Enter: ")
                write_record(
                    operator_log,
                    {
                        "kind": "checkpoint_confirmed",
                        "checkpoint": index,
                        "scheduled_at_seconds": int(checkpoint["at_seconds"]),
                        "confirmed_at": utc_now(),
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "action": action,
                    },
                )

            end = started + duration
            while not stop_requested.is_set() and time.monotonic() < end:
                stop_requested.wait(min(30, end - time.monotonic()))
    except (EOFError, KeyboardInterrupt):
        stop_requested.set()
    finally:
        elapsed = round(time.monotonic() - started, 3)
        completed = not stop_requested.is_set() and elapsed >= duration
        stop_requested.set()
        collector.join(timeout=5)
        manifest.update(
            {
                "ended_at": utc_now(),
                "elapsed_seconds": elapsed,
                "status": "completed" if completed else "interrupted",
                "expected_checkpoints": len(checkpoints),
            }
        )
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Soak run {manifest['status']}; evidence is in {args.output}")


if __name__ == "__main__":
    main()
