"""Billing, Stripe and Quota Engine

Revision ID: 003_billing_and_quotas
Revises: 002_organizations_and_rbac
Create Date: 2026-10-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_billing_and_quotas"
down_revision: Union[str, None] = "002_organizations_and_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. billing_events
    op.create_table(
        "billing_events",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("stripe_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_billing_events_stripe_id", "billing_events", ["stripe_event_id"], unique=True)

    # 2. scan_usage
    op.create_table(
        "scan_usage",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            sa.CHAR(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scans_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scan_usage_org_id", "scan_usage", ["org_id"])
    op.create_index("ix_scan_usage_org_period", "scan_usage", ["org_id", "period_start", "period_end"])


def downgrade() -> None:
    op.drop_table("scan_usage")
    op.drop_table("billing_events")
