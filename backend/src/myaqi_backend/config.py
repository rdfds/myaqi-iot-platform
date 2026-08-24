from __future__ import annotations

import os
from dataclasses import dataclass

DEVELOPMENT_MASTER_KEY = "development-only-change-this-key-before-deploying"


@dataclass(frozen=True)
class Settings:
    database_url: str
    device_master_key: str
    auth_clock_skew_seconds: int
    max_batch_size: int
    max_content_length: int
    outbox_batch_size: int
    outbox_max_attempts: int
    outbox_lock_timeout_seconds: int
    log_level: str
    environment: str
    service_version: str
    revision: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "sqlite+pysqlite:///myaqi-development.db",
            ),
            device_master_key=os.getenv("DEVICE_MASTER_KEY", DEVELOPMENT_MASTER_KEY),
            auth_clock_skew_seconds=int(os.getenv("AUTH_CLOCK_SKEW_SECONDS", "300")),
            max_batch_size=int(os.getenv("MAX_BATCH_SIZE", "500")),
            max_content_length=int(os.getenv("MAX_CONTENT_LENGTH", str(512 * 1024))),
            outbox_batch_size=int(os.getenv("OUTBOX_BATCH_SIZE", "100")),
            outbox_max_attempts=int(os.getenv("OUTBOX_MAX_ATTEMPTS", "8")),
            outbox_lock_timeout_seconds=int(os.getenv("OUTBOX_LOCK_TIMEOUT_SECONDS", "60")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            environment=os.getenv("APP_ENVIRONMENT", "development"),
            service_version=os.getenv("SERVICE_VERSION", "0.1.0-dev"),
            revision=os.getenv("APP_REVISION", "local"),
        )

    def as_flask_config(self) -> dict[str, object]:
        return {
            "DATABASE_URL": self.database_url,
            "DEVICE_MASTER_KEY": self.device_master_key,
            "AUTH_CLOCK_SKEW_SECONDS": self.auth_clock_skew_seconds,
            "MAX_BATCH_SIZE": self.max_batch_size,
            "MAX_CONTENT_LENGTH": self.max_content_length,
            "OUTBOX_BATCH_SIZE": self.outbox_batch_size,
            "OUTBOX_MAX_ATTEMPTS": self.outbox_max_attempts,
            "OUTBOX_LOCK_TIMEOUT_SECONDS": self.outbox_lock_timeout_seconds,
            "LOG_LEVEL": self.log_level,
            "APP_ENVIRONMENT": self.environment,
            "SERVICE_VERSION": self.service_version,
            "APP_REVISION": self.revision,
        }
