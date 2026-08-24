"""Create reliable device-ingestion schema.

Revision ID: 20260823_0001
Revises:
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ingest_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id",
            "idempotency_key",
            name="uq_ingest_requests_device_idempotency",
        ),
    )
    op.create_index(
        "ix_ingest_requests_created_at", "ingest_requests", ["created_at"], unique=False
    )
    op.create_table(
        "measurements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("ingest_request_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("pm25_ug_m3", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("relative_humidity", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_request_id"], ["ingest_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "sequence", name="uq_measurements_device_sequence"),
    )
    op.create_index(
        "ix_measurements_device_observed",
        "measurements",
        ["device_id", "observed_at"],
        unique=False,
    )
    op.create_index("ix_measurements_received_at", "measurements", ["received_at"], unique=False)
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_type", "aggregate_id", name="uq_outbox_event_aggregate"),
    )
    op.create_index(
        "ix_outbox_events_available",
        "outbox_events",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_locked",
        "outbox_events",
        ["status", "locked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_locked", table_name="outbox_events")
    op.drop_index("ix_outbox_events_available", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_measurements_received_at", table_name="measurements")
    op.drop_index("ix_measurements_device_observed", table_name="measurements")
    op.drop_table("measurements")
    op.drop_index("ix_ingest_requests_created_at", table_name="ingest_requests")
    op.drop_table("ingest_requests")
    op.drop_table("devices")
