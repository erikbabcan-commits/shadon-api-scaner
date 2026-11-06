#!/usr/bin/env python3
"""Restore an approved private PG archive into a disposable Unix-socket-only DB.

No source database connection is made. No API, worker or integrations are started.
The snapshot manifest stays private; the output contains no row data or counts.
Use the frozen backend dev environment as this script's Python interpreter.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

import asyncpg
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps/api"
ADDED_COLUMNS = {
    "findings": ["cvss_score", "cvss_vector", "poc_command", "remediation_patch"],
    "alert_events": ["attempt_count", "next_attempt_at", "lease_token", "lease_expires_at"],
}


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def run(command, **kwargs):
    # Never forward pg_restore/migration stderr: it can contain archived data.
    subprocess.run(command, check=True, capture_output=True, **kwargs)


async def inspect(socket_path, expected_tables):
    connection = await asyncpg.connect(host=str(socket_path), user="straz_restore", database="straz_restore", command_timeout=120)
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        counts, hashes = {}, {}
        for name in expected_tables:
            schema, table = name.split(".", 1)
            relation = quote(schema) + "." + quote(table)
            counts[name] = await connection.fetchval("SELECT count(*) FROM " + relation)
            if table == "alembic_version":
                continue
            row = "to_jsonb(t)"
            if table in ADDED_COLUMNS:
                row += " - ARRAY[" + ",".join("'" + column + "'" for column in ADDED_COLUMNS[table]) + "]::text[]"
            hashes[name] = await connection.fetchval(
                "SELECT encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') "
                "FROM (SELECT encode(sha256(convert_to((" + row + ")::text,'UTF8')),'hex') h FROM " + relation + " t) rows"
            )
        return revision, counts, hashes
    finally:
        await connection.close()


async def verify_audit(socket_path):
    connection = await asyncpg.connect(host=str(socket_path), user="straz_restore", database="straz_restore")
    try:
        row = await connection.fetchval("SELECT id FROM audit_events LIMIT 1")
        if row is None:
            return {"row_mutation_test": "not exercised: no audit rows"}
        verified = {}
        for action, query in (("update", "UPDATE audit_events SET action=action WHERE id=$1"), ("delete", "DELETE FROM audit_events WHERE id=$1")):
            transaction = connection.transaction()
            await transaction.start()
            try:
                try:
                    await connection.execute(query, row)
                except asyncpg.PostgresError as error:
                    verified[action + "_rejected"] = "immutable" in str(error).lower() or "cannot be deleted" in str(error).lower()
                else:
                    verified[action + "_rejected"] = False
            finally:
                await transaction.rollback()
        if not all(verified.values()):
            raise RuntimeError("Restored audit protection failed")
        return verified
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--postgres-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New sanitized JSON result file")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output file; preserve earlier evidence")
    manifest = json.loads(args.manifest.read_text())
    digest = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    if digest != manifest["archive_sha256"]:
        raise RuntimeError("Archive checksum does not match approved snapshot manifest")
    pg = args.postgres_bin.resolve()
    scratch = Path(tempfile.mkdtemp(prefix="straz-restore-"))
    started = False
    result = None
    try:
        run([str(pg / "initdb"), "-D", str(scratch / "db"), "-U", "straz_restore", "-A", "trust", "--no-locale"])
        options = shlex.join(["-h", "", "-k", str(scratch), "-p", "5432", "-c", "shared_buffers=16MB", "-c", "max_connections=15"])
        run([str(pg / "pg_ctl"), "-D", str(scratch / "db"), "-l", str(scratch / "postgres.log"), "-o", options, "-w", "start"])
        started = True
        run([str(pg / "createdb"), "-h", str(scratch), "-U", "straz_restore", "straz_restore"])
        run([str(pg / "pg_restore"), "-h", str(scratch), "-U", "straz_restore", "-d", "straz_restore", "--exit-on-error", "--no-owner", "--no-privileges", str(args.archive.resolve())])
        before, counts, hashes = asyncio.run(inspect(scratch, manifest["snapshot_consistent_counts"]))
        if [before] != manifest["alembic_revision"] or counts != manifest["snapshot_consistent_counts"]:
            raise RuntimeError("Restored revision or row counts differ from source snapshot")
        audit_before = asyncio.run(verify_audit(scratch))
        url = URL.create("postgresql+asyncpg", username="straz_restore", database="straz_restore", query={"host": str(scratch)}).render_as_string(hide_password=False)
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT"}}
        env.update({"DATABASE_URL": url, "STRAZ_ENV": "test", "STRAZ_ADMIN_PASSWORD": os.urandom(24).hex(), "STRAZ_SESSION_SECRET": os.urandom(32).hex()})
        run([sys.executable, "-m", "app.migrations", "upgrade"], cwd=API, env=env)
        after, counts_after, hashes_after = asyncio.run(inspect(scratch, manifest["snapshot_consistent_counts"]))
        if counts_after != counts or hashes_after != hashes:
            raise RuntimeError("Upgrade changed original application rows")
        run([sys.executable, "-c", "import asyncio; from app.migrations import assert_schema_at_head; asyncio.run(assert_schema_at_head())"], cwd=API, env=env)
        audit_after = asyncio.run(verify_audit(scratch))
        if hashlib.sha256(args.archive.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Source archive unexpectedly changed")
        migrations = sorted((API / "alembic/versions").glob("*.py"))
        result = {
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "before_revision": before, "after_revision": after,
            "source_archive_checksum_verified": True,
            "restored_counts_match_source_snapshot": True,
            "original_application_data_hashes_preserved": True,
            "compared_application_tables": len(hashes),
            "audit_before": audit_before, "audit_after": audit_after,
            "current_head_startup_guard_passed": True,
            "restore_isolation": "Private owner-only Unix socket, TCP disabled; no API, worker, scheduler or integrations",
            "production_database_modified": False,
            "migration_files": [{"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in migrations],
        }
    finally:
        if started:
            # If shutdown fails, preserve files rather than deleting a live DB.
            run([str(pg / "pg_ctl"), "-D", str(scratch / "db"), "-m", "fast", "-w", "stop"])
        shutil.rmtree(scratch)
    result["restored_working_copy_removed"] = True
    with open(args.output, "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print("Private archive restored and upgraded; original data preserved; disposable database removed")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, asyncpg.PostgresError, subprocess.SubprocessError):
        print("Restore verification failed; no success claimed. Raw archived data and diagnostics are not printed.", file=sys.stderr)
        raise SystemExit(1)
