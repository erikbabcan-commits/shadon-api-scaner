"""Rehearse the 008/009 startup boundary and rollback on new throwaway databases."""
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import db, migrations


PG = os.environ.get("STRAZ_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG, reason="STRAZ_TEST_PG_URL not set")
API = Path(__file__).resolve().parents[1]
REV8 = "008_postgres_uuid_and_audit_fk"
REV9 = "009_cvss_and_poc_fields"


def test_cutover_rejects_mixed_versions_and_can_return_to_008(monkeypatch, tmp_path):
    target = make_url(PG)
    assert target.host in {"127.0.0.1", "localhost", "::1"}, "Only loopback test servers are permitted"
    name = "straz_cutover_" + uuid.uuid4().hex

    async def admin(sql):
        engine = create_async_engine(target, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                await connection.execute(text(sql))
        finally:
            await engine.dispose()

    url = target.set(database=name).render_as_string(hide_password=False)
    engine = create_async_engine(url, poolclass=NullPool)
    monkeypatch.setattr(db, "engine", engine)

    def config(directory):
        result = Config()
        result.set_main_option("script_location", str(directory))
        return result

    old = tmp_path / "old-alembic"
    shutil.copytree(API / "alembic", old, ignore=shutil.ignore_patterns("__pycache__", "009_*.py"))
    failing = tmp_path / "failing-alembic"
    shutil.copytree(API / "alembic", failing, ignore=shutil.ignore_patterns("__pycache__"))
    revision = failing / "versions/009_cvss_and_poc_fields.py"
    revision.write_text(revision.read_text().replace(
        "\n\ndef downgrade()", "\n    raise RuntimeError('synthetic migration failure')\n\ndef downgrade()"
    ))

    def migrate(*arguments, directory=None, succeeds=True):
        env = {**os.environ, "DATABASE_URL": url, "STRAZ_ENV": "test"}
        script = (
            "from alembic.config import Config; from alembic import command; "
            f"c=Config({str(API / 'alembic.ini')!r}); "
            f"c.set_main_option('script_location',{str(directory or API / 'alembic')!r}); "
            f"command.{arguments[0]}(c,{arguments[1]!r})"
        )
        result = subprocess.run([sys.executable, "-c", script], cwd=API, env=env, capture_output=True)
        assert (result.returncode == 0) is succeeds, "Unexpected migration result (credentials suppressed)"

    async def query(sql):
        async with engine.begin() as connection:
            return (await connection.execute(text(sql))).all()

    async def execute(sql):
        async with engine.begin() as connection:
            await connection.execute(text(sql))

    def guard(directory, accepted):
        monkeypatch.setattr(migrations, "get_alembic_config", lambda: config(directory))
        if accepted:
            asyncio.run(migrations.assert_schema_at_head())
        else:
            with pytest.raises(RuntimeError, match="not at Alembic head"):
                asyncio.run(migrations.assert_schema_at_head())

    asyncio.run(admin(f'CREATE DATABASE "{name}" TEMPLATE template0'))
    try:
        migrate("upgrade", REV8)
        app_id, finding_id = uuid.uuid4(), uuid.uuid4()
        asyncio.run(execute(f"INSERT INTO apps(id,name,base_url) VALUES('{app_id}','cutover','https://example.invalid')"))
        asyncio.run(execute(
            "INSERT INTO findings(id,app_id,source,title,fingerprint) VALUES "
            f"('{finding_id}','{app_id}','http','preserve this finding','cutover-fixture')"
        ))
        guard(old, True)
        guard(API / "alembic", False)
        migrate("upgrade", "head", directory=failing, succeeds=False)
        assert asyncio.run(query("SELECT version_num FROM alembic_version")) == [(REV8,)]
        assert asyncio.run(query("SELECT count(*) FROM information_schema.columns WHERE table_name='findings' AND column_name='cvss_score'")) == [(0,)]
        guard(old, True)

        migrate("upgrade", "head")
        guard(API / "alembic", True)
        guard(old, False)
        assert asyncio.run(query("SELECT version_num FROM alembic_version")) == [(REV9,)]
        assert asyncio.run(query("SELECT title,cvss_score,poc_command FROM findings")) == [("preserve this finding", None, None)]
        asyncio.run(execute("UPDATE findings SET cvss_score=7.5,poc_command='synthetic-poc'"))
        # This downgrade is safe only in the disposable test DB: it demonstrates loss of 009 fields.
        migrate("downgrade", REV8)
        guard(old, True)
        guard(API / "alembic", False)
        assert asyncio.run(query("SELECT title FROM findings")) == [("preserve this finding",)]
        migrate("upgrade", "head")
        guard(API / "alembic", True)
        assert asyncio.run(query("SELECT cvss_score,poc_command FROM findings")) == [(None, None)]
    finally:
        asyncio.run(engine.dispose())
        asyncio.run(admin(f'DROP DATABASE "{name}" WITH (FORCE)'))
