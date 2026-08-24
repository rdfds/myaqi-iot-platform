"""Track device runtime state for fleet diagnostics.

Revision ID: 20260824_0002
Revises: 20260823_0001
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0002"
down_revision: str | None = "20260823_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("last_firmware_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("last_sequence", sa.Integer(), nullable=True),
    )
    op.create_index("ix_devices_last_seen_at", "devices", ["last_seen_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_devices_last_seen_at", table_name="devices")
    op.drop_column("devices", "last_sequence")
    op.drop_column("devices", "last_firmware_version")
    op.drop_column("devices", "last_seen_at")
