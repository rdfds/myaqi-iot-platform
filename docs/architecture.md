# System architecture

## Context

myAQI contains two explicit system generations. The historical generation paired CircuitPython devices with provider-specific Flask routes. The reference generation keeps the device concerns but replaces the backend boundary with durable, authenticated batch ingestion.

## Reference runtime flow

1. A device buffers readings locally and assigns each reading a monotonic sequence number.
2. It sends up to 500 readings with a stable idempotency key and an HMAC signature over the exact request.
3. The API authenticates the active device, validates the complete batch, and reserves the idempotency key.
4. PostgreSQL inserts unseen `(device_id, sequence)` rows and ignores sequences already committed by an earlier retry.
5. The API stores its response and a `measurements.ingested` outbox event in the same transaction.
6. One of several workers claims available events with `FOR UPDATE SKIP LOCKED` and hands them to a downstream adapter.
7. Failed handoffs retry with backoff. Exhausted events remain in a dead-letter state for operator review.

## Boundaries and failure behavior

| Component | Responsibility | Failure behavior |
| --- | --- | --- |
| CircuitPython firmware | Sensor reads, provisioning, buffering, sequence assignment | Retain buffered readings and reuse the same request identity until acknowledged |
| Ingestion API | Authentication, validation, idempotency, persistence | Reject the entire invalid batch; never acknowledge before commit |
| PostgreSQL | Source of truth for devices, requests, readings, and outbox | Unique constraints enforce both deduplication layers under concurrency |
| Outbox worker | Durable downstream handoff | Exclusive claims, stale-lock recovery, bounded retry, dead-letter state |
| Downstream publisher | Alerts, queues, or analytics | May fail without rolling back already accepted sensor data |
| Prometheus/log collector | Operational visibility | Telemetry failure does not alter ingestion correctness |

## Data model

- `devices`: active device identities and key versions
- `ingest_requests`: immutable `(device, idempotency key, payload hash)` records plus the committed response
- `measurements`: sensor observations unique by `(device, sequence)`
- `outbox_events`: downstream work with claim, retry, and publication state

## Transaction boundaries

The ingestion transaction includes the idempotency reservation, unseen measurements, response body, and outbox event. This avoids the dual-write failure where data commits but the alert event is lost, or the event publishes for data that later rolls back.

Workers use a separate transaction to claim rows, perform external work without holding database locks, and then use a short ownership-checked transaction to mark success or failure.

## Deployment topology

`compose.yaml` is a reproducible local topology, not a production platform recommendation. A deployment should run migrations as a release step, place API instances behind TLS, use managed PostgreSQL, export metrics and logs, and replace the logging publisher with an explicit downstream adapter.
