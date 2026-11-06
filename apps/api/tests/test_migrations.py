"""Exercise migrations against isolated databases rather than ORM-created tables."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


API_ROOT = Path(__file__).resolve().parents[1]


def _alembic(database_url, *args):
    # A separate process keeps settings caches and the live development DB untouched.
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        env={**os.environ, "DATABASE_URL": database_url, "STRAZ_ENV": "test"},
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_sqlite_upgrade_preserves_data_and_downgrade(tmp_path):
    database_path = tmp_path / "migrations.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    _alembic(database_url, "upgrade", "001_initial_schema")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO apps (id, name, base_url) VALUES (?, ?, ?)",
            ("11111111-1111-4111-8111-111111111111", "Legacy app", "https://example.invalid"),
        )
        connection.execute(
            "INSERT INTO audit_events (id, action) VALUES (?, ?)",
            ("22222222-2222-4222-8222-222222222222", "legacy.event"),
        )

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "009_cvss_and_poc_fields",
        )
        assert connection.execute("SELECT name, organization_id FROM apps").fetchone() == (
            "Legacy app", None,
        )
        assert connection.execute("SELECT action FROM audit_events").fetchone() == ("legacy.event",)
        for table in ("apps", "audit_events"):
            foreign_keys = connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            assert any(
                row[2] == "organizations" and row[3] == "organization_id" and row[6] == "CASCADE"
                for row in foreign_keys
            )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute("UPDATE apps SET organization_id='missing'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE audit_events SET action='changed'")
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute("DELETE FROM audit_events")

    _alembic(database_url, "downgrade", "base")
    with sqlite3.connect(database_path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        assert tables == [("alembic_version",)]
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == []


def test_postgresql_batch_foreign_keys_keep_historical_names():
    # Offline rendering never opens a connection, including when PostgreSQL is unavailable.
    sql = _alembic("postgresql+asyncpg://127.0.0.1/migration_test", "upgrade", "head", "--sql")
    normalized_sql = " ".join(sql.split())
    for table in ("apps", "audit_events"):
        assert (
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_organization_id_fkey "
            "FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE"
        ) in normalized_sql
