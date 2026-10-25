"""Integrations and Alerting

Revision ID: 005_integrations_and_alerting
Revises: 004_branding_and_compliance
Create Date: 2026-10-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005_integrations_and_alerting"
down_revision: Union[str, None] = "004_branding_and_compliance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. alert_channels
    op.create_table(
        "alert_channels",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            sa.CHAR(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "app_id",
            sa.CHAR(36),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("destination_url", sa.String(500), nullable=False),
        sa.Column("secret_token", sa.String(255), nullable=True),
        sa.Column("min_severity", sa.String(16), server_default="high", nullable=False),
        sa.Column("events", sa.Text(), server_default='["finding.created","app.down"]', nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alert_channels_org_id", "alert_channels", ["org_id"])
    op.create_index("ix_alert_channels_app_id", "alert_channels", ["app_id"])

    # 2. alert_events
    op.create_table(
        "alert_events",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            sa.CHAR(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "app_id",
            sa.CHAR(36),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "channel_id",
            sa.CHAR(36),
            sa.ForeignKey("alert_channels.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alert_events_org_id", "alert_events", ["org_id"])
    op.create_index("ix_alert_events_channel_id", "alert_events", ["channel_id"])


def downgrade() -> None:
    op.drop_table("alert_events")
    op.drop_table("alert_channels")
