from __future__ import annotations

import argparse
import json
import math
import os
import signal
import statistics
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy import func, select

from myaqi_backend.admin import provision_device, verify_sequence_range
from myaqi_backend.auth import decode_device_secret, sign_request
from myaqi_backend.config import Settings
from myaqi_backend.database import make_engine, make_session_factory
from myaqi_backend.models import IngestRequest, Measurement, OutboxEvent
from myaqi_backend.outbox import outbox_health


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


@dataclass(frozen=True)
class Batch:
    first_sequence: int
    last_sequence: int
    idempotency_key: str
    body: bytes

    @property
    def size(self) -> int:
        return self.last_sequence - self.first_sequence + 1


@dataclass(frozen=True)
class UploadResult:
    status: int
    body: dict[str, object]
    replayed: bool
    latency_ms: float


class UploadUnavailable(RuntimeError):
    pass


def build_batches(*, readings: int, batch_size: int, run_id: str) -> list[Batch]:
    if readings < 1 or batch_size < 1 or batch_size > 500:
        raise ValueError("readings and batch_size must be positive; batch_size cannot exceed 500")
    observed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    batches: list[Batch] = []
    for first in range(1, readings + 1, batch_size):
        last = min(readings, first + batch_size - 1)
        payload = {
            "readings": [
                {
                    "sequence": sequence,
                    "observed_at": observed_at,
                    "pm25_ug_m3": round(8.0 + (sequence % 800) / 20, 2),
                }
                for sequence in range(first, last + 1)
            ]
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        batches.append(
            Batch(
                first_sequence=first,
                last_sequence=last,
                idempotency_key=f"software-trial-{run_id[:12]}-{first}-{last}",
                body=body,
            )
        )
    return batches


def post_batch(
    *,
    base_url: str,
    device_id: str,
    device_secret: bytes,
    batch: Batch,
) -> UploadResult:
    path = f"/v1/devices/{device_id}/measurements:batch"
    timestamp = str(int(time.time()))
    request = Request(
        base_url.rstrip("/") + path,
        data=batch.body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": batch.idempotency_key,
            "X-Device-Timestamp": timestamp,
            "X-Device-Signature": sign_request(
                device_secret,
                timestamp,
                "POST",
                path,
                batch.body,
            ),
            "X-Firmware-Version": "software-fault-trial-v1",
        },
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - controlled trial URL
            payload = json.loads(response.read())
            return UploadResult(
                status=response.status,
                body=payload,
                replayed=response.headers.get("Idempotent-Replayed") == "true",
                latency_ms=(time.perf_counter() - started) * 1000,
            )
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"Ingestion returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise UploadUnavailable(str(error.reason)) from error


@dataclass
class ManagedProcess:
    name: str
    command: list[str]
    log_path: Path
    environment: dict[str, str]
    process: subprocess.Popen[bytes] | None = field(default=None, init=False)
    starts: int = field(default=0, init=False)
    _log_handle: object | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError(f"{self.name} is already running")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("ab")
        self.process = subprocess.Popen(  # noqa: S603 - fixed local commands
            self.command,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            env=self.environment,
            start_new_session=True,
        )
        self.starts += 1

    def assert_running(self) -> None:
        if self.process is None or self.process.poll() is not None:
            code = None if self.process is None else self.process.returncode
            raise RuntimeError(f"{self.name} is not running (exit code {code})")

    def stop(self, *, grace_seconds: float = 10) -> None:
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.process = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


def wait_for_api(base_url: str, process: ManagedProcess, *, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        process.assert_running()
        try:
            with urlopen(base_url.rstrip("/") + "/health/ready", timeout=2) as response:  # noqa: S310
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.2)
    raise TimeoutError("API did not become ready")


def wait_for_outbox(factory, *, timeout_seconds: float = 30) -> dict[str, int | float]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, int | float] = {}
    while time.monotonic() < deadline:
        latest = outbox_health(factory)
        if latest["pending"] == 0 and latest["processing"] == 0 and latest["dead"] == 0:
            return latest
        time.sleep(0.2)
    raise TimeoutError(f"Outbox did not drain: {latest}")


def database_report(
    *,
    device_id: str,
    readings: int,
    settings: Settings,
) -> dict[str, object]:
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            measurement_count = session.scalar(
                select(func.count())
                .select_from(Measurement)
                .where(Measurement.device_id == device_id)
            )
            distinct_sequences = session.scalar(
                select(func.count(func.distinct(Measurement.sequence))).where(
                    Measurement.device_id == device_id
                )
            )
            ingest_requests = session.scalar(
                select(func.count()).select_from(IngestRequest).where(
                    IngestRequest.device_id == device_id
                )
            )
            outbox_counts = {
                status: count
                for status, count in session.execute(
                    select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(
                        OutboxEvent.status
                    )
                )
            }
        sequence_report = verify_sequence_range(
            device_id,
            start=1,
            end=readings,
            settings=settings,
        )
        return {
            "measurements": measurement_count,
            "distinct_sequences": distinct_sequences,
            "duplicate_rows": int(measurement_count or 0) - int(distinct_sequences or 0),
            "ingest_requests": ingest_requests,
            "outbox": outbox_counts,
            "sequence_range": sequence_report,
        }
    finally:
        engine.dispose()


def round_robin_operations(
    *, api_faults: int, worker_faults: int, acknowledgement_replays: int
) -> list[str]:
    remaining = {
        "api_outage": api_faults,
        "worker_outage": worker_faults,
        "acknowledgement_replay": acknowledgement_replays,
    }
    operations: list[str] = []
    while any(remaining.values()):
        for name in remaining:
            if remaining[name]:
                operations.append(name)
                remaining[name] -= 1
    return operations


def run_trial(args: argparse.Namespace) -> dict[str, object]:
    if min(args.api_faults, args.worker_faults, args.acknowledgement_replays) < 0:
        raise ValueError("fault counts cannot be negative")
    if args.outage_buffer_batches < 1 or args.outage_seconds < 0:
        raise ValueError("outage buffer batches must be positive and outage seconds nonnegative")
    parsed_url = urlparse(args.base_url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("the software trial may start processes only on a local HTTP origin")
    port = parsed_url.port or 80

    output_directory = args.output.parent
    output_directory.mkdir(parents=True, exist_ok=True)
    settings = Settings.from_env()
    run_id = str(uuid.uuid4())
    device_id = f"software-trial-{run_id[:8]}"
    batches = deque(
        build_batches(readings=args.readings, batch_size=args.batch_size, run_id=run_id)
    )
    initial_batch_count = len(batches)
    operations = round_robin_operations(
        api_faults=args.api_faults,
        worker_faults=args.worker_faults,
        acknowledgement_replays=args.acknowledgement_replays,
    )
    minimum_fault_batches = (args.api_faults + args.worker_faults) * args.outage_buffer_batches
    if initial_batch_count < minimum_fault_batches + args.acknowledgement_replays:
        raise ValueError("not enough batches for the configured fault plan")

    device = provision_device(device_id, "Automated software reliability trial", settings=settings)
    secret = decode_device_secret(str(device["device_secret"]))
    process_environment = dict(os.environ)
    api = ManagedProcess(
        name="api",
        command=[
            "gunicorn",
            f"--bind={parsed_url.hostname}:{port}",
            "--workers=2",
            "--threads=4",
            "--access-logfile=-",
            "myaqi_backend.wsgi:app",
        ],
        log_path=output_directory / "api.log",
        environment=process_environment,
    )
    worker = ManagedProcess(
        name="outbox-worker",
        command=["myaqi-worker", "--poll-seconds", "0.05"],
        log_path=output_directory / "worker.log",
        environment=process_environment,
    )

    started_at = utc_now()
    started = time.monotonic()
    latencies: list[float] = []
    faults: list[dict[str, object]] = []
    uploaded_batches = 0
    replayed_batches = 0
    failed_upload_attempts = 0
    accepted_readings = 0
    max_device_queue = 0
    max_outbox_pending = 0

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    def send(batch: Batch, *, expect_replay: bool = False) -> UploadResult:
        nonlocal accepted_readings, replayed_batches, uploaded_batches
        result = post_batch(
            base_url=args.base_url,
            device_id=device_id,
            device_secret=secret,
            batch=batch,
        )
        if result.status != 202:
            raise RuntimeError(f"unexpected ingestion status {result.status}")
        acknowledged = int(result.body.get("accepted", 0)) + int(
            result.body.get("duplicates", 0)
        )
        if acknowledged != batch.size:
            raise RuntimeError("ingestion acknowledgement did not cover the complete batch")
        if result.replayed != expect_replay:
            raise RuntimeError(
                f"expected replay={expect_replay}, received replay={result.replayed}"
            )
        latencies.append(result.latency_ms)
        if expect_replay:
            replayed_batches += 1
        else:
            uploaded_batches += 1
            accepted_readings += int(result.body.get("accepted", 0))
        return result

    def send_steady(count: int) -> None:
        for _ in range(min(count, len(batches))):
            send(batches.popleft())

    try:
        api.start()
        wait_for_api(args.base_url, api)
        worker.start()
        worker.assert_running()

        for operation_index, operation in enumerate(operations):
            operations_left = len(operations) - operation_index
            reserved = sum(
                args.outage_buffer_batches
                if upcoming in {"api_outage", "worker_outage"}
                else 1
                for upcoming in operations[operation_index:]
            )
            steady_count = max(0, (len(batches) - reserved) // (operations_left + 1))
            send_steady(steady_count)

            fault_started = time.monotonic()
            if operation == "api_outage":
                api.stop()
                buffered = [batches.popleft() for _ in range(args.outage_buffer_batches)]
                buffered_readings = sum(batch.size for batch in buffered)
                max_device_queue = max(max_device_queue, buffered_readings)
                try:
                    post_batch(
                        base_url=args.base_url,
                        device_id=device_id,
                        device_secret=secret,
                        batch=buffered[0],
                    )
                except UploadUnavailable:
                    failed_upload_attempts += 1
                else:
                    raise RuntimeError("upload unexpectedly succeeded while the API was stopped")
                time.sleep(args.outage_seconds)
                api.start()
                wait_for_api(args.base_url, api)
                for batch in buffered:
                    send(batch)
                faults.append(
                    {
                        "kind": operation,
                        "buffered_readings": buffered_readings,
                        "duration_seconds": round(time.monotonic() - fault_started, 3),
                        "recovered": True,
                    }
                )
            elif operation == "worker_outage":
                worker.stop()
                buffered = [batches.popleft() for _ in range(args.outage_buffer_batches)]
                for batch in buffered:
                    send(batch)
                health_during_outage = outbox_health(factory)
                max_outbox_pending = max(
                    max_outbox_pending,
                    int(health_during_outage["pending"]),
                )
                time.sleep(args.outage_seconds)
                worker.start()
                worker.assert_running()
                wait_for_outbox(factory)
                faults.append(
                    {
                        "kind": operation,
                        "queued_outbox_events": int(health_during_outage["pending"]),
                        "duration_seconds": round(time.monotonic() - fault_started, 3),
                        "recovered": True,
                    }
                )
            else:
                batch = batches.popleft()
                first_result = send(batch)
                replay_result = send(batch, expect_replay=True)
                faults.append(
                    {
                        "kind": operation,
                        "batch": [batch.first_sequence, batch.last_sequence],
                        "first_request_id": first_result.body.get("request_id"),
                        "replay_request_id": replay_result.body.get("request_id"),
                        "same_request_identity": first_result.body.get("request_id")
                        == replay_result.body.get("request_id"),
                        "recovered": True,
                    }
                )

        send_steady(len(batches))
        wait_for_outbox(factory, timeout_seconds=60)
        api.assert_running()
        worker.assert_running()
    finally:
        worker.stop()
        api.stop()
        engine.dispose()

    database = database_report(device_id=device_id, readings=args.readings, settings=settings)
    duration_seconds = time.monotonic() - started
    checks = {
        "all_readings_acknowledged": accepted_readings == args.readings,
        "all_sequences_present": database["sequence_range"]["complete"] is True,
        "no_missing_sequences": database["sequence_range"]["missing"] == 0,
        "no_duplicate_rows": database["duplicate_rows"] == 0,
        "one_ingest_request_per_unique_batch": database["ingest_requests"]
        == initial_batch_count,
        "all_outbox_events_published": database["outbox"].get("published", 0)
        == initial_batch_count,
        "no_pending_outbox_events": database["outbox"].get("pending", 0) == 0,
        "no_dead_outbox_events": database["outbox"].get("dead", 0) == 0,
        "all_faults_recovered": len(faults) == len(operations)
        and all(fault["recovered"] for fault in faults),
        "all_acknowledgement_replays_idempotent": replayed_batches
        == args.acknowledgement_replays
        and all(
            fault.get("same_request_identity", True)
            for fault in faults
            if fault["kind"] == "acknowledgement_replay"
        ),
    }
    github_repository = os.getenv("GITHUB_REPOSITORY")
    github_run_id = os.getenv("GITHUB_RUN_ID")
    run_url = (
        f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{github_repository}/actions/runs/"
        f"{github_run_id}"
        if github_repository and github_run_id
        else None
    )
    return {
        "schema_version": 1,
        "trial": "software-fault-injection",
        "scope": {
            "runtime": "GitHub-hosted runner" if os.getenv("GITHUB_ACTIONS") else "local process",
            "database": "PostgreSQL",
            "device": "software simulator",
            "hardware_tested": False,
            "aws_deployment_tested": False,
        },
        "run_id": run_id,
        "run_url": run_url,
        "revision": os.getenv("GITHUB_SHA") or args.revision,
        "device_id": device_id,
        "started_at": started_at,
        "ended_at": utc_now(),
        "duration_seconds": round(duration_seconds, 3),
        "configuration": {
            "readings": args.readings,
            "batch_size": args.batch_size,
            "unique_batches": initial_batch_count,
            "api_faults": args.api_faults,
            "worker_faults": args.worker_faults,
            "acknowledgement_replays": args.acknowledgement_replays,
            "outage_buffer_batches": args.outage_buffer_batches,
            "outage_seconds": args.outage_seconds,
        },
        "metrics": {
            "accepted_readings": accepted_readings,
            "uploaded_batches": uploaded_batches,
            "replayed_batches": replayed_batches,
            "failed_upload_attempts": failed_upload_attempts,
            "api_restarts": max(0, api.starts - 1),
            "worker_restarts": max(0, worker.starts - 1),
            "max_device_queue_readings": max_device_queue,
            "max_outbox_pending": max_outbox_pending,
            "throughput_readings_per_second": round(args.readings / duration_seconds, 2),
            "request_latency_ms": {
                "mean": round(statistics.fmean(latencies), 2),
                "p50": round(percentile(latencies, 0.50), 2),
                "p95": round(percentile(latencies, 0.95), 2),
                "p99": round(percentile(latencies, 0.99), 2),
            },
        },
        "faults": faults,
        "database": database,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a software fault-injection trial against PostgreSQL and real services"
    )
    parser.add_argument("--readings", type=int, default=25_000)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--api-faults", type=int, default=4)
    parser.add_argument("--worker-faults", type=int, default=3)
    parser.add_argument("--acknowledgement-replays", type=int, default=8)
    parser.add_argument("--outage-buffer-batches", type=int, default=5)
    parser.add_argument("--outage-seconds", type=float, default=1.5)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--revision", default="local")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.readings < 1 or args.readings > 1_000_000:
        raise SystemExit("--readings must be between 1 and 1,000,000")
    report = run_trial(args)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
