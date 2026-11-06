"""Recover notification outbox claims with fenced leases and bounded retries.

Revision ID: 010_alert_outbox_leases
Revises: 009_cvss_and_poc_fields
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010_alert_outbox_leases"
down_revision = "009_cvss_and_poc_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_events", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("alert_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alert_events", sa.Column("lease_token", sa.CHAR(36).with_variant(postgresql.UUID(as_uuid=True), "postgresql"), nullable=True))
    op.add_column("alert_events", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_alert_events_status_next_attempt", "alert_events", ["status", "next_attempt_at"])
    op.create_index("ix_alert_events_status_lease_expiry", "alert_events", ["status", "lease_expires_at"])


def downgrade() -> None:
    # Destructive: retry counters and in-flight ownership are lost. Stop all
    # delivery workers and preserve a backup before any approved downgrade.
    op.drop_index("ix_alert_events_status_lease_expiry", table_name="alert_events")
    op.drop_index("ix_alert_events_status_next_attempt", table_name="alert_events")
    op.drop_column("alert_events", "lease_expires_at")
    op.drop_column("alert_events", "lease_token")
    op.drop_column("alert_events", "next_attempt_at")
    op.drop_column("alert_events", "attempt_count")
