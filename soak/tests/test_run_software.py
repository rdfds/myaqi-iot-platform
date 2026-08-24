from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from soak.run_software import build_batches, percentile, round_robin_operations  # noqa: E402


def test_build_batches_covers_sequence_range_without_gaps() -> None:
    batches = build_batches(readings=1_025, batch_size=100, run_id="1234567890abcdef")

    assert len(batches) == 11
    assert batches[0].first_sequence == 1
    assert batches[0].last_sequence == 100
    assert batches[-1].first_sequence == 1_001
    assert batches[-1].last_sequence == 1_025
    assert sum(batch.size for batch in batches) == 1_025
    assert len({batch.idempotency_key for batch in batches}) == len(batches)
    assert [
        reading["sequence"]
        for batch in batches
        for reading in json.loads(batch.body)["readings"]
    ] == list(range(1, 1_026))


def test_build_batches_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        build_batches(readings=100, batch_size=501, run_id="trial")


def test_fault_plan_interleaves_available_operations() -> None:
    operations = round_robin_operations(
        api_faults=3,
        worker_faults=2,
        acknowledgement_replays=4,
    )

    assert operations[:3] == [
        "api_outage",
        "worker_outage",
        "acknowledgement_replay",
    ]
    assert operations.count("api_outage") == 3
    assert operations.count("worker_outage") == 2
    assert operations.count("acknowledgement_replay") == 4


def test_percentile_uses_nearest_rank() -> None:
    values = [5.0, 1.0, 3.0, 2.0, 4.0]

    assert percentile(values, 0.50) == 3.0
    assert percentile(values, 0.95) == 5.0
    assert percentile([], 0.95) == 0.0
