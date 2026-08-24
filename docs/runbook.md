# Backend runbook

## Release

1. Build the backend image from a reviewed commit.
2. Back up PostgreSQL and verify available migration headroom.
3. Run `alembic upgrade head` as a one-off release step.
4. Start API instances, then workers.
5. Confirm `/health/ready`, ingestion success rate, latency, and outbox backlog.

## Signals

- `myaqi_ingest_requests_total{outcome=...}`: accepted, replayed, and conflicting requests
- `myaqi_ingested_readings_total{outcome=...}`: accepted and duplicate readings
- `myaqi_authentication_failures_total`: invalid, unknown, or stale device requests
- `myaqi_ingest_duration_seconds`: API latency distribution
- structured request logs with request ID, status, path, and duration

Queue health queries:

```sql
SELECT status, count(*)
FROM outbox_events
GROUP BY status;

SELECT id, event_type, attempts, available_at, last_error
FROM outbox_events
WHERE status = 'dead'
ORDER BY created_at;
```

## Common incidents

### Authentication failures rise

Check device clocks, key version, provisioning state, and whether a proxy rewrites the path. Do not widen the timestamp window before confirming clock synchronization.

### Outbox backlog grows

Inspect downstream availability and worker logs. Scaling workers is safe because claims use `SKIP LOCKED`; it will not fix a permanently failing publisher.

### Events remain `processing`

Workers automatically reclaim locks older than `OUTBOX_LOCK_TIMEOUT_SECONDS`. Confirm no event legitimately takes longer than that before lowering the timeout.

### Dead events require replay

Correct the downstream cause, audit the payload, then move selected rows to `pending`, clear lock fields, reset `available_at`, and retain `attempts` for history. Automate and audit this operation before production use.

## Rollback

Application rollback is preferred when a schema change is backward compatible. Do not run an Alembic downgrade blindly on a populated database; review data-loss implications and restore from a tested backup when necessary.
