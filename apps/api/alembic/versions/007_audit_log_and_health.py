"""Audit log immutability and health

Revision ID: 007_audit_log_and_health
Revises: 006_api_keys_and_ci
Create Date: 2026-10-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "007_audit_log_and_health"
down_revision: Union[str, None] = "006_api_keys_and_ci"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add enterprise audit columns to audit_events
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "organization_id",
                sa.CHAR(36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "actor_email",
                sa.String(255),
                server_default="system",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("ip_address", sa.String(45), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("details", sa.JSON(), nullable=True))

        batch_op.create_index("ix_audit_events_organization_id", ["organization_id"])
        batch_op.create_index("ix_audit_events_action", ["action"])
        batch_op.create_index("ix_audit_events_org_created", ["organization_id", "created_at"])

    # 2. Database-level immutability triggers (SQLite & PostgreSQL)
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_audit_events_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Audit log records are immutable and cannot be updated');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_audit_events_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Audit log records cannot be deleted');
            END;
            """
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_audit_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Audit log records are immutable and cannot be modified or deleted';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_events_no_update') THEN
                    CREATE TRIGGER trg_audit_events_no_update
                    BEFORE UPDATE ON audit_events
                    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_events_no_delete') THEN
                    CREATE TRIGGER trg_audit_events_no_delete
                    BEFORE DELETE ON audit_events
                    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS prevent_audit_events_update;")
        op.execute("DROP TRIGGER IF EXISTS prevent_audit_events_delete;")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events;")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete ON audit_events;")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation();")

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_index("ix_audit_events_org_created")
        batch_op.drop_index("ix_audit_events_action")
        batch_op.drop_index("ix_audit_events_organization_id")
        batch_op.drop_column("details")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("ip_address")
        batch_op.drop_column("actor_email")
        batch_op.drop_column("organization_id")
