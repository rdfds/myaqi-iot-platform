from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_ingestion import counts


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL is required for the concurrent idempotency test",
)
def test_concurrent_replays_commit_exactly_once(app, signed_post, measurement_batch) -> None:
    def submit(_index: int) -> int:
        with app.test_client() as client:
            response = signed_post(client, measurement_batch)
            return response.status_code

    with ThreadPoolExecutor(max_workers=12) as executor:
        statuses = list(executor.map(submit, range(24)))

    assert statuses == [202] * 24
    assert counts(app) == (1, 2, 1)
