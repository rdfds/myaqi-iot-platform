# Software fault-injection trial — 2026-08-24

**Result:** PASS  
**Tested revision:** [`722e28d`](https://github.com/rdfds/myaqi-iot-platform/commit/722e28d0b779a479cfa53a349e3ae3c9edb7920e)  
**GitHub Actions run:** [32750547307](https://github.com/rdfds/myaqi-iot-platform/actions/runs/32750547307)

## Scope

This run exercised the real Flask API, two Gunicorn workers, the outbox-worker process, Alembic
migrations, signed batch ingestion, and PostgreSQL 16 on a GitHub-hosted runner. The device was a
software generator. This result is not evidence of physical sensor behavior, CircuitPython flash
durability, AWS deployment, TLS/DNS behavior, long-duration uptime, or production load.

## Fault plan and observed results

| Signal | Observed value |
|---|---:|
| Sequential readings | 50,000 |
| Unique signed batches | 500 |
| API outages and restarts | 6 |
| Worker outages and restarts | 4 |
| Deliberately replayed acknowledgements | 12 |
| Maximum buffered readings during an API outage | 500 |
| Maximum queued outbox events during a worker outage | 6 |
| Persisted measurements | 50,000 |
| Distinct persisted sequences | 50,000 |
| Missing sequence values | 0 |
| Duplicate database rows | 0 |
| Published outbox events | 500 |
| Pending or dead outbox events at verification | 0 |
| Request latency p95 | 56.38 ms |
| Fault-injection phase duration | 48.767 s |

Each API outage stopped both Gunicorn workers, buffered five 100-reading batches, confirmed that an
upload failed while the service was unavailable, restarted the service, and drained the buffered
data. Each worker outage continued accepting readings while event publication was stopped, then
verified that the backlog drained after restart. Each acknowledgement replay reused the exact body
and idempotency key and returned the original request identity without another measurement or event.

The p95 value describes sequential batch requests within this runner and should not be presented as
a concurrent-load benchmark. The total duration includes the injected outage windows.

## Pass conditions

The run failed unless all of these checks evaluated true:

- all 50,000 generated readings were acknowledged;
- the exact sequence interval `1..50000` existed in PostgreSQL;
- no measurement sequence appeared more than once;
- the database contained one ingest request and one outbox event per unique batch;
- all 500 outbox events reached `published`, with no pending or dead events;
- every service interruption recovered; and
- all 12 acknowledgement replays retained the original request identity.

The Actions artifact retained the machine-readable JSON result and complete API/worker logs. The
artifact has a 30-day retention period; the linked workflow run and this scoped summary provide the
durable public record.
