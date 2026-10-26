"""PostgreSQL-only: 007 -> 008 upgrade with existing data.

Set STRAZ_TEST_PG_URL to an EMPTY throwaway database, e.g.
postgresql+asyncpg://user:pw@127.0.0.1:5432/scratch
"""
import asyncio
import os
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

PG = os.environ.get("STRAZ_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG, reason="STRAZ_TEST_PG_URL not set")

U = "11111111-1111-4111-8111-111111111111"
O = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _alembic(*args):
    env = {**os.environ, "DATABASE_URL": PG}
    subprocess.run([sys.executable, "-m", "alembic", *args], env=env, check=True, capture_output=True)


async def _run(*stmts, fetch=None):
    eng = create_async_engine(PG)
    try:
        async with eng.begin() as c:
            for s in stmts:
                await c.execute(text(s))
            if fetch:
                return (await c.execute(text(fetch))).all()
    finally:
        await eng.dispose()


def test_upgrade_preserves_data_and_audit_survives_deletes():
    tables = asyncio.run(_run(fetch="select tablename from pg_tables where schemaname=current_schema()"))
    assert tables == [], "STRAZ_TEST_PG_URL must point to an empty throwaway database"
    _alembic("upgrade", "007_audit_log_and_health")
    asyncio.run(_run(
        f"insert into users(id,email,password_hash) values('{U}','a@x.test','h')",
        f"insert into organizations(id,name,slug) values('{O}','o','o')",
        f"insert into audit_events(id,user_id,organization_id,action) values"
        f"('99999999-9999-4999-8999-999999999991','{U}','{O}','a.one'),"
        f"('99999999-9999-4999-8999-999999999992','00000000-0000-4000-8000-0000000000ee',null,'orphan')",
    ))
    _alembic("upgrade", "head")
    rows = asyncio.run(_run(fetch="select data_type from information_schema.columns "
                                  "where table_name='users' and column_name='id'"))
    assert rows[0][0] == "uuid"
    for column in ("user_id", "organization_id"):
        with pytest.raises(Exception, match="immutable"):
            asyncio.run(_run(f"update audit_events set {column}=null where action='a.one'"))
    asyncio.run(_run(f"delete from organizations where id='{O}'", f"delete from users where id='{U}'"))
    rows = asyncio.run(_run(fetch="select count(*), count(user_id), count(organization_id) from audit_events"))
    assert tuple(rows[0]) == (2, 1, 0)  # nothing deleted; valid refs nulled, pre-existing orphan untouched
    for bad in ("delete from audit_events", "update audit_events set action='x'"):
        with pytest.raises(Exception, match="immutable"):
            asyncio.run(_run(bad))

    # A rollback and invalid legacy data must not leave a partially converted schema.
    _alembic("downgrade", "007_audit_log_and_health")
    asyncio.run(_run("insert into users(id,email,password_hash) values('not-a-uuid','invalid@example.invalid','fixture')"))
    with pytest.raises(subprocess.CalledProcessError):
        _alembic("upgrade", "head")
    rows = asyncio.run(_run(fetch="select version_num from alembic_version"))
    assert rows[0][0] == "007_audit_log_and_health"
    rows = asyncio.run(_run(fetch="select data_type from information_schema.columns "
                                 "where table_schema=current_schema() and table_name='users' and column_name='id'"))
    assert rows[0][0] == "character"
    asyncio.run(_run("delete from users where id='not-a-uuid'"))
    _alembic("upgrade", "head")
    rows = asyncio.run(_run(fetch="select count(*) from audit_events"))
    assert rows[0][0] == 2
