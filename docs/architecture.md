# System architecture

## Runtime flow

1. The CircuitPython device reads PM2.5, assigns a monotonic sequence number, and commits the reading to its local JSON state before attempting network I/O.
2. The device selects a bounded batch. Its body and idempotency key remain stable across connection loss, process reset, and HTTP retry.
3. After synchronizing its UTC clock with NTP, the device signs the exact request with its provisioned secret and posts it over HTTPS.
4. The API authenticates the active device, validates the complete batch, and reserves the `(device, idempotency key)` pair.
5. PostgreSQL inserts unseen `(device_id, sequence)` rows and ignores sequences already committed by an earlier request.
6. The API stores the response and a `measurements.ingested` outbox event in the same transaction.
7. The device removes the batch only after a `202` response accounts for every reading as accepted or duplicate.
8. Workers claim outbox events with `FOR UPDATE SKIP LOCKED`, hand them to a downstream adapter, and record success or scheduled retry.

## Boundaries and failure behavior

| Component | Responsibility | Failure behavior |
| --- | --- | --- |
| CircuitPython firmware | Sensor reads, provisioning, durable queue, sequence assignment, signing | Retain the batch until a complete acknowledgement; cap storage and count discarded oldest readings |
| Ingestion API | Authentication, validation, idempotency, persistence | Reject an invalid batch atomically; never acknowledge before commit |
| PostgreSQL | Source of truth for devices, requests, readings, and outbox | Unique constraints enforce both deduplication layers under concurrency |
| Outbox worker | Durable downstream handoff | Exclusive claims, stale-lock recovery, bounded retry, dead-letter state |
| Downstream publisher | Alerts, queues, or analytics | May fail without rolling back accepted sensor data |
| Prometheus/log collector | Operational visibility | Telemetry failure does not alter ingestion correctness |

## Device persistence

The firmware state contains `next_sequence`, `pending`, and `dropped_readings`. Every mutation is written and synced to a temporary file, the last complete primary is retained as a backup, and the temporary file is promoted and synced as primary. On boot, a malformed primary falls back to the last complete backup. If no valid primary, backup, or temporary state remains, ingestion fails closed instead of resetting the sequence and silently reusing device identities.

The queue is deliberately bounded because flash is finite. When it is full, the oldest reading is removed and `dropped_readings` increments. That counter makes prolonged-offline data loss explicit rather than silent.

## Data model

- `devices`: active device identities and key versions
- `ingest_requests`: immutable `(device, idempotency key, payload hash)` records plus the committed response
- `measurements`: sensor observations unique by `(device, sequence)`
- `outbox_events`: downstream work with claim, retry, and publication state

## Transaction boundaries

The ingestion transaction includes the idempotency reservation, unseen measurements, committed response, and outbox event. This prevents both halves of a dual-write failure: measurement data without its event, or an event for data that later rolls back.

Workers use a separate transaction to claim rows, perform external work without holding database locks, and then use a short ownership-checked transaction to mark success or failure.

## Deployment topology

`compose.yaml` provides a reproducible local topology. A deployment should run migrations as a release step, place API instances behind TLS, use managed PostgreSQL, export metrics and logs, and replace the included logging publisher with an explicit alert, queue, or analytics adapter.

The retired provider-specific adapter remains under `legacy/` for implementation traceability and is outside this runtime path.
