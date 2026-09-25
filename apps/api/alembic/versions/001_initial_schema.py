"""Initial database schema with all models and performance indexes

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-25 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. apps
    op.create_table(
        "apps",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("environment", sa.String(50), server_default="prod", nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("heartbeat_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("tls_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("http_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("safe_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("internetdb_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("subdomain_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("ports_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("trivy_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("gitleaks_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("git_url", sa.String(500), nullable=True),
        sa.Column("image_ref", sa.String(500), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_title", sa.String(500), nullable=True),
        sa.Column("last_up", sa.Boolean(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. targets
    op.create_table(
        "targets",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("app_id", sa.CHAR(36), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("verify_token", sa.String(64), nullable=False),
        sa.Column("verify_method", sa.String(50), nullable=True),
        sa.Column("trusted_private", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_targets_app_id", "targets", ["app_id"])

    # 4. scan_runs
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("app_id", sa.CHAR(36), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.CHAR(36), nullable=True),
    )
    op.create_index("ix_scan_runs_app_id", "scan_runs", ["app_id"])
    op.create_index("ix_scan_runs_app_created", "scan_runs", ["app_id", "created_at"])
    op.create_index("ix_scan_runs_status", "scan_runs", ["status"])

    # 5. findings
    op.create_table(
        "findings",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("app_id", sa.CHAR(36), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.CHAR(36), sa.ForeignKey("targets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), server_default="info", nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("app_id", "fingerprint", name="uq_finding_fingerprint"),
    )
    op.create_index("ix_findings_app_id", "findings", ["app_id"])
    op.create_index("ix_findings_app_status", "findings", ["app_id", "status"])
    op.create_index("ix_findings_status_last_seen", "findings", ["status", "last_seen_at"])

    # 6. audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.CHAR(36), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("findings")
    op.drop_table("scan_runs")
    op.drop_table("targets")
    op.drop_table("apps")
    op.drop_table("users")
