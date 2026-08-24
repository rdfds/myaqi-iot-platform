from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from myaqi_backend.auth import decode_device_secret, sign_request


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def post_batch(base_url: str, device: dict[str, str], sequence: int) -> tuple[int, float]:
    path = f"/v1/devices/{device['device_id']}/measurements:batch"
    observed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = json.dumps(
        {
            "readings": [
                {
                    "sequence": sequence,
                    "observed_at": observed_at,
                    "pm25_ug_m3": 12.5 + (sequence % 20),
                }
            ]
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(time.time()))
    signature = sign_request(
        decode_device_secret(device["device_secret"]),
        timestamp,
        "POST",
        path,
        body,
    )
    request = Request(
        base_url.rstrip("/") + path,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": f"benchmark-{device['device_id']}-{sequence:012d}",
            "X-Device-Timestamp": timestamp,
            "X-Device-Signature": signature,
        },
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - operator-supplied URL
            response.read()
            status = response.status
    except HTTPError as exc:
        exc.read()
        status = exc.code
    except URLError:
        status = 0
    return status, (time.perf_counter() - started) * 1000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a reproducible myAQI ingestion benchmark")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--devices", type=Path, default=Path("benchmark-devices.json"))
    parser.add_argument("--requests", type=int, default=10_000)
    parser.add_argument("--concurrency", type=int, default=50)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    devices = json.loads(args.devices.read_text(encoding="utf-8"))["devices"]
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                post_batch,
                args.base_url,
                devices[index % len(devices)],
                index + 1,
            )
            for index in range(args.requests)
        ]
        for future in as_completed(futures):
            status, latency = future.result()
            statuses[status] = statuses.get(status, 0) + 1
            latencies.append(latency)

    duration = time.perf_counter() - started
    result = {
        "requests": args.requests,
        "concurrency": args.concurrency,
        "duration_seconds": round(duration, 3),
        "throughput_requests_per_second": round(args.requests / duration, 2),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "p99": round(percentile(latencies, 0.99), 2),
        },
        "status_counts": {str(key): value for key, value in sorted(statuses.items())},
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
