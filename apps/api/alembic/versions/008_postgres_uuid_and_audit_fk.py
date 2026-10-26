"""PostgreSQL native UUID columns and audit-log FK/trigger compatibility

Revision ID: 008_postgres_uuid_and_audit_fk
Revises: 007_audit_log_and_health
Create Date: 2026-10-26 20:00:00.000000

Migrations 001-007 are published and untouched. On PostgreSQL this revision:

* validates that every CHAR(36) identifier is a well-formed UUID (aborts and
  changes nothing otherwise) and converts them to native UUID, re-creating all
  foreign keys with their original definitions;
* makes audit_events FKs ``ON DELETE SET NULL`` (the user FK is added NOT VALID
  so pre-existing orphaned audit rows are kept untouched) and relaxes the
  immutability trigger so ONLY the FK-driven nulling of user_id /
  organization_id is permitted. Audit rows are never deleted, and any other
  UPDATE or any DELETE is still rejected;
* adds indexes declared in the models that were missing.

On other dialects (SQLite test DBs) this is a no-op: GUID is CHAR(36) there.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008_postgres_uuid_and_audit_fk"
down_revision: Union[str, None] = "007_audit_log_and_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID_COLUMNS = [
    ("alert_channels", "app_id"), ("alert_channels", "id"), ("alert_channels", "org_id"),
    ("alert_events", "app_id"), ("alert_events", "channel_id"), ("alert_events", "id"),
    ("alert_events", "org_id"),
    ("api_keys", "id"), ("api_keys", "organization_id"), ("api_keys", "user_id"),
    ("apps", "id"), ("apps", "organization_id"),
    ("audit_events", "id"), ("audit_events", "organization_id"), ("audit_events", "user_id"),
    ("billing_events", "id"),
    ("findings", "app_id"), ("findings", "id"), ("findings", "target_id"),
    ("organization_invitations", "id"), ("organization_invitations", "org_id"),
    ("organization_members", "id"), ("organization_members", "org_id"),
    ("organization_members", "user_id"),
    ("organizations", "id"),
    ("scan_run_findings", "finding_id"), ("scan_run_findings", "scan_run_id"),
    ("scan_runs", "app_id"), ("scan_runs", "created_by"), ("scan_runs", "id"),
    ("scan_usage", "id"), ("scan_usage", "org_id"),
    ("targets", "app_id"), ("targets", "id"),
    ("users", "id"),
]

_UUID_RE = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def _retype(target_type: str, using_suffix: str) -> None:
    """Drop FKs touching the tables, retype all columns, restore the FKs."""
    tables = sorted({t for t, _ in UUID_COLUMNS})
    table_list = ",".join(f"'{t}'" for t in tables)
    op.execute(
        f"""
        DO $mig$
        DECLARE r record;
        BEGIN
            CREATE TEMP TABLE _straz_fk(name text, tbl text, def text) ON COMMIT DROP;
            FOR r IN
                SELECT c.conname, c.conrelid::regclass::text AS tbl,
                       pg_get_constraintdef(c.oid) AS def
                FROM pg_constraint c
                WHERE c.contype = 'f'
                  AND c.connamespace = current_schema()::regnamespace
                  AND c.conrelid::regclass::text IN ({table_list})
            LOOP
                INSERT INTO _straz_fk VALUES (r.conname, r.tbl, r.def);
                EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
            END LOOP;
            {"".join(
                f"EXECUTE 'ALTER TABLE {t} ALTER COLUMN {c} TYPE {target_type} USING {c}{using_suffix}';"
                for t, c in UUID_COLUMNS
            )}
            FOR r IN SELECT * FROM _straz_fk LOOP
                EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s', r.tbl, r.name, r.def);
            END LOOP;
        END $mig$;
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 1. Refuse to touch anything if any identifier is not a valid UUID.
    checks = " UNION ALL ".join(
        f"SELECT '{t}.{c}' AS col, count(*) AS bad FROM {t} "
        f"WHERE {c} IS NOT NULL AND {c}::text !~ '{_UUID_RE}'"
        for t, c in UUID_COLUMNS
    )
    op.execute(
        f"""
        DO $mig$
        DECLARE r record;
        BEGIN
            FOR r IN SELECT * FROM ({checks}) q WHERE bad > 0 LOOP
                RAISE EXCEPTION 'Migration 008 aborted: % invalid UUID value(s) in %',
                    r.bad, r.col;
            END LOOP;
        END $mig$;
        """
    )

    # 2. CHAR(36) -> native UUID (+ FK re-creation). audit_events has no
    #    FK on user_id yet, so orphaned values (if any) convert fine.
    _retype("uuid", "::uuid")

    # 3. Audit FKs: never cascade-delete audit rows; null the reference instead.
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_organization_id_fkey")
    op.execute(
        "ALTER TABLE audit_events ADD CONSTRAINT audit_events_organization_id_fkey "
        "FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL NOT VALID"
    )
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_user_id_fkey")
    op.execute(
        "ALTER TABLE audit_events ADD CONSTRAINT audit_events_user_id_fkey "
        "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL NOT VALID"
    )

    # 4. UPDATE trigger: allow only the FK-driven nulling of the two references.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_update()
        RETURNS TRIGGER AS $$
        BEGIN
            IF pg_trigger_depth() > 1
               AND (NEW.user_id IS DISTINCT FROM OLD.user_id
                    OR NEW.organization_id IS DISTINCT FROM OLD.organization_id)
               AND (to_jsonb(NEW) - 'user_id' - 'organization_id')
                   = (to_jsonb(OLD) - 'user_id' - 'organization_id')
               AND (NEW.user_id IS NOT DISTINCT FROM OLD.user_id
                    OR (NEW.user_id IS NULL AND NOT EXISTS
                        (SELECT 1 FROM users WHERE id = OLD.user_id)))
               AND (NEW.organization_id IS NOT DISTINCT FROM OLD.organization_id
                    OR (NEW.organization_id IS NULL AND NOT EXISTS
                        (SELECT 1 FROM organizations WHERE id = OLD.organization_id)))
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Audit log records are immutable and cannot be modified or deleted';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events")
    op.execute(
        "CREATE TRIGGER trg_audit_events_no_update BEFORE UPDATE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_audit_update()"
    )

    # 5. Indexes declared by the models but never created.
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_events_app_id ON alert_events (app_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_created_at ON audit_events (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_entity_type ON audit_events (entity_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_user_id ON audit_events (user_id)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Restore original strict trigger and CASCADE org FK; audit rows kept.
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events")
    op.execute(
        "CREATE TRIGGER trg_audit_events_no_update BEFORE UPDATE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation()"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_update()")
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_user_id_fkey")
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_organization_id_fkey")
    op.execute(
        "ALTER TABLE audit_events ADD CONSTRAINT audit_events_organization_id_fkey "
        "FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE NOT VALID"
    )
    _retype("char(36)", "::text")
