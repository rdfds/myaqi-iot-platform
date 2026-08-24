from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self.ingest_requests = Counter(
            "myaqi_ingest_requests_total",
            "Device ingestion requests by outcome",
            ("outcome",),
            registry=self.registry,
        )
        self.ingested_readings = Counter(
            "myaqi_ingested_readings_total",
            "Readings accepted or deduplicated",
            ("outcome",),
            registry=self.registry,
        )
        self.authentication_failures = Counter(
            "myaqi_authentication_failures_total",
            "Rejected device authentication attempts",
            registry=self.registry,
        )
        self.ingest_latency = Histogram(
            "myaqi_ingest_duration_seconds",
            "End-to-end ingestion request duration",
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
            registry=self.registry,
        )
        self.outbox_events = Counter(
            "myaqi_outbox_events_total",
            "Outbox processing outcomes",
            ("outcome",),
            registry=self.registry,
        )
