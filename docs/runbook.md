# Backend runbook

## Release

The protected `Deploy AWS` workflow is the release path. It checks out the SHA that passed `main` CI, assumes the deployment role through GitHub OIDC, builds one immutable ARM64 image, waits for ECR scanning, applies Alembic migrations, updates the worker, and starts the API canary. Do not bypass the environment approval for a routine release.

Before approval:

1. Confirm the schema change is backward compatible with both the old and new API tasks.
2. Review the Terraform plan separately if the release changes infrastructure.
3. Confirm RDS backup status, free storage, and no pre-existing alarm state.
4. Confirm the GitHub summary names the expected commit SHA and image tag.

During and after deployment:

1. Watch both target groups while ECS sends 10% of traffic to the new revision.
2. Confirm the migration task exits `0`, worker heartbeat returns, and outbox age declines.
3. Confirm `GET /health/ready` reports the released revision after the traffic shift.
4. Retain the GitHub deployment URL, ECS deployment ID, and alarm timeline as release evidence.

ECS automatically rolls back a canary when its circuit breaker or configured production alarms fire. The workflow restores the previous API and worker task definitions if a later smoke or alarm check fails. Database rollback is deliberately separate: migrations must follow expand/migrate/contract so application rollback remains safe.

## Signals

- `myaqi_ingest_requests_total{outcome=...}`: accepted, replayed, and conflicting requests
- `myaqi_ingested_readings_total{outcome=...}`: accepted and duplicate readings
- `myaqi_authentication_failures_total`: invalid, unknown, or stale device requests
- `myaqi_ingest_duration_seconds`: API latency distribution
- structured request logs with request ID, status, path, and duration
- Route 53 `HealthCheckStatus` and `TimeToFirstByte` from global external checkers
- CloudWatch alarms for target health, 5xx responses, p95 latency, ECS task count, worker heartbeat, outbox age/dead events, RDS CPU, and RDS free storage

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

Correct the downstream cause and audit the event before replaying it:

```bash
myaqi-admin list-dead-events --limit 100
myaqi-admin replay-event <event-id>
```

Replay retains the prior attempt count and error for operator context. A subsequent publish failure can return the event to `dead` immediately; do not repeatedly replay a failing downstream dependency.

## Production debugging

Start with immutable identifiers and read-only checks. Record the active health revision, GitHub deployment URL, CloudWatch alarm transition, request ID, device ID, and UTC time window before changing state.

```bash
myaqi-admin inspect-device <device-id>
myaqi-admin verify-sequence-range <device-id> --start <first> --end <last>
myaqi-admin list-dead-events --limit 100
```

Use CloudWatch Logs Insights to correlate `request_id`, `device_id`, `event_id`, and `worker_id`. ECS Exec is enabled for controlled diagnosis inside a running task, but it requires an authorized operator session and should not be used to edit the container. Never print environment variables or secret values into a ticket, terminal transcript, or incident document.

For a missing device interval, compare three boundaries:

1. The board diagnostic's `next_sequence`, pending range, drop counter, and last acknowledged sequence.
2. `inspect-device` server heartbeat, firmware release, and persisted range.
3. `verify-sequence-range` against the exact expected interval.

This separates sensor/flash loss, offline buffering, authentication failure, API rejection, and downstream outbox delay without guessing from a single metric.

## Incident response

1. Acknowledge the alarm and open a UTC incident timeline from [`incidents/template.md`](incidents/template.md).
2. Establish impact from the external health check, ingestion counters, affected devices, and sequence ranges.
3. Identify the active and previous application revisions. If the incident began with a deployment and rollback is schema-safe, restore the previous task definitions.
4. Contain downstream failures by stopping unsafe replays; do not disable authentication or widen the clock-skew window as a first response.
5. Verify recovery from global health, API revision, worker heartbeat, queue age, dead events, and device sequence completeness.
6. Preserve sanitized logs and deployment/alarm links, then write contributing factors and concrete follow-up work.

No incident record should be invented to make the repository look operated. Add a post-incident document only after a real event or a clearly labeled game-day exercise.

## Rollback

Application rollback is preferred when a schema change is backward compatible. Do not run an Alembic downgrade blindly on a populated database; review data-loss implications and restore from a tested backup when necessary.
