"""Organizations, Multi-Tenancy and RBAC

Revision ID: 002_organizations_and_rbac
Revises: 001_initial_schema
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_organizations_and_rbac"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. organizations table
    op.create_table(
        "organizations",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("billing_email", sa.String(320), nullable=True),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("plan_tier", sa.String(50), server_default="free", nullable=False),
        sa.Column("subscription_status", sa.String(50), server_default="active", nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custom_logo_url", sa.String(500), nullable=True),
        sa.Column("brand_color", sa.String(7), server_default="#0284c7", nullable=True),
        sa.Column("report_footer_text", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_stripe_customer", "organizations", ["stripe_customer_id"])

    # 2. organization_members table
    op.create_table(
        "organization_members",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
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
        sa.Column("role", sa.String(16), server_default="member", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "user_id", name="uq_org_member"),
    )
    op.create_index("ix_org_members_org_id", "organization_members", ["org_id"])
    op.create_index("ix_org_members_user_id", "organization_members", ["user_id"])

    # 3. organization_invitations table
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            sa.CHAR(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), server_default="member", nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_org_invitations_token", "organization_invitations", ["token"], unique=True)
    op.create_index("ix_org_invitations_org_id", "organization_invitations", ["org_id"])

    # 4. Add organization_id to apps
    with op.batch_alter_table("apps") as batch_op:
        batch_op.add_column(
            sa.Column(
                "organization_id",
                sa.CHAR(36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_apps_organization_id", ["organization_id"])


def downgrade() -> None:
    with op.batch_alter_table("apps") as batch_op:
        batch_op.drop_index("ix_apps_organization_id")
        batch_op.drop_column("organization_id")

    op.drop_table("organization_invitations")
    op.drop_table("organization_members")
    op.drop_table("organizations")
