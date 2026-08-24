# ADR 0001: Use a transactional outbox for downstream work

- Status: accepted
- Date: 2026-08-23

## Context

Ingestion must acknowledge sensor data quickly, while alerts and analytics may depend on unavailable external services. Writing a measurement and publishing an event as two independent operations creates a dual-write gap.

## Decision

Store a downstream event in PostgreSQL in the same transaction as the accepted measurements. Separate workers claim committed events with `FOR UPDATE SKIP LOCKED`, publish outside the claim transaction, and record success or retry state with an ownership check.

## Consequences

- accepted data always has a durable downstream work item;
- provider outages do not force devices to resend already committed data;
- delivery is at least once, so consumers must use the event ID idempotently;
- the database becomes a small durable queue and requires backlog monitoring;
- event ordering is creation-oriented, not a global strict ordering guarantee.

Kafka or a managed queue can replace the publisher boundary later without changing the ingestion transaction.
