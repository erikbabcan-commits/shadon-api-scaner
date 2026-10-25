"""API keys and CI/CD

Revision ID: 006_api_keys_and_ci
Revises: 005_integrations_and_alerting
Create Date: 2026-10-24 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006_api_keys_and_ci"
down_revision: Union[str, None] = "005_integrations_and_alerting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. api_keys
    op.create_table(
        "api_keys",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.CHAR(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scopes", sa.JSON(), server_default='["ci:scan", "apps:read"]', nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["organization_id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # 2. scan_run_findings
    op.create_table(
        "scan_run_findings",
        sa.Column(
            "scan_run_id",
            sa.CHAR(36),
            sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            sa.CHAR(36),
            sa.ForeignKey("findings.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("observed_severity", sa.String(20), nullable=False),
        sa.Column("is_new", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scan_run_findings_run", "scan_run_findings", ["scan_run_id"])
    op.create_index("ix_scan_run_findings_finding", "scan_run_findings", ["finding_id"])

    # 3. Add columns to scan_runs
    op.add_column("scan_runs", sa.Column("ci_fail_on", sa.String(20), nullable=True))
    op.add_column("scan_runs", sa.Column("observations_complete", sa.Boolean(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("scan_runs", "observations_complete")
    op.drop_column("scan_runs", "ci_fail_on")
    op.drop_table("scan_run_findings")
    op.drop_table("api_keys")
