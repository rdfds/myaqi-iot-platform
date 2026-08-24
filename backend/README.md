# Backend

The backend receives authenticated measurement batches from the CircuitPython client, persists readings and downstream work atomically, and exposes the health and telemetry needed to operate that path.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=sqlite+pysqlite:///myaqi-development.db
export DEVICE_MASTER_KEY=development-only-change-this-key-before-deploying
alembic upgrade head
myaqi-admin provision-device local-001 --name "Local development sensor"
gunicorn --bind 127.0.0.1:8000 myaqi_backend.wsgi:app
```

SQLite is supported for local development and fast tests. PostgreSQL is the deployment target and is required for meaningful concurrent `SKIP LOCKED` behavior.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local SQLite file | SQLAlchemy connection URL |
| `DB_HOST`, `DB_PORT`, `DB_NAME` | unset | Managed PostgreSQL location when `DATABASE_URL` is absent |
| `DB_USER`, `DB_PASSWORD` | unset | Managed database credentials; ECS injects RDS secret JSON fields |
| `DEVICE_MASTER_KEY` | unsafe development value | Root key for versioned per-device secrets |
| `AUTH_CLOCK_SKEW_SECONDS` | `300` | Accepted device timestamp window |
| `MAX_BATCH_SIZE` | `500` | Maximum readings per ingestion request |
| `MAX_CONTENT_LENGTH` | `524288` | Maximum request bytes |
| `OUTBOX_BATCH_SIZE` | `100` | Events claimed by a worker in one transaction |
| `OUTBOX_MAX_ATTEMPTS` | `8` | Failures before dead-letter state |
| `OUTBOX_LOCK_TIMEOUT_SECONDS` | `60` | Age at which an abandoned processing lock is reclaimable |
| `OUTBOX_HEALTH_INTERVAL_SECONDS` | `60` | Structured queue-health heartbeat interval |
| `OUTBOX_SNS_TOPIC_ARN` | unset | SNS destination; unset uses the local logging publisher |
| `LOG_LEVEL` | `INFO` | Structured application log level |
| `APP_ENVIRONMENT` | `development` | Environment included in health metadata |
| `SERVICE_VERSION` | `0.1.0-dev` | Human-readable release version |
| `APP_REVISION` | `local` | Immutable Git revision included in health metadata |

## Schema changes

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe the change"
alembic check
```

The initial schema stores devices, immutable ingestion requests, measurements, and transactional outbox events. Both idempotency guarantees are database-backed unique constraints.

## Test commands

Fast local suite:

```bash
pytest
```

PostgreSQL suite, including concurrent replay:

```bash
export TEST_DATABASE_URL=postgresql+psycopg://myaqi:password@localhost:5432/myaqi_test
pytest
```

Quality checks:

```bash
ruff check .
pytest --cov=myaqi_backend --cov-report=term-missing
alembic check
```

## Outbox behavior

`myaqi-worker` claims a bounded batch, commits the claims, then publishes each event. A successful handoff marks the row `published`. A failed handoff clears the lock and schedules exponential backoff; the final failure moves the event to `dead` for operator review.

`OUTBOX_SNS_TOPIC_ARN` selects the production SNS publisher. Without it, the worker uses the deliberately narrow logging publisher for local development. Both adapters preserve event ID and type; only an ownership-checked database transaction marks a claimed event published.

The worker logs queue counts, oldest pending age, and dead events on a fixed heartbeat, completes an in-flight batch after `SIGTERM`, then exits. The AWS deployment converts these JSON fields into CloudWatch metrics and alarms.

## Operator commands

```bash
myaqi-admin inspect-device school-001
myaqi-admin verify-sequence-range school-001 --start 1 --end 500
myaqi-admin list-dead-events --limit 100
myaqi-admin replay-event <event-id>
```

These commands run inside the trusted network boundary and avoid exposing a public admin API. See [`../docs/runbook.md`](../docs/runbook.md) for diagnosis and replay constraints.
