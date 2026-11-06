"""Actual PostgreSQL locks, fencing and 008/009→010 preservation; no delivery."""
import asyncio
from datetime import timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import Base
from app.models import AlertEvent
from app.services import notifications
from test_notification_outbox import NOW, seed


PG = os.environ.get("STRAZ_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG, reason="STRAZ_TEST_PG_URL not set")
API = Path(__file__).resolve().parents[1]
REV10 = "010_alert_outbox_leases"


@pytest_asyncio.fixture
async def pg_database():
    target = make_url(PG)
    assert target.host in {"127.0.0.1", "localhost", "::1"}, "Only disposable loopback test servers are allowed"
    name = "straz_outbox_" + uuid.uuid4().hex
    admin = create_async_engine(target, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
    url = target.set(database=name).render_as_string(hide_password=False)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        yield engine, async_sessionmaker(engine, expire_on_commit=False), url
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


@pytest_asyncio.fixture
async def pg_outbox(pg_database, monkeypatch):
    engine, factory, _ = pg_database
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    clock = [NOW]
    monkeypatch.setattr(notifications, "_utcnow", lambda: clock[0])
    monkeypatch.setattr("app.db.SessionLocal", factory)
    return engine, factory, clock


async def test_postgres_skips_locked_rows_and_concurrent_consumers_do_not_share_claims(pg_outbox):
    _, factory, _ = pg_outbox
    async with factory() as db:
        *_, first = await seed(db)
        *_, second = await seed(db)
    async with factory() as holder:
        await holder.scalar(select(AlertEvent).where(AlertEvent.id == first.id).with_for_update())
        # This must return promptly while a separate transaction owns the row.
        claims = await asyncio.wait_for(notifications._claim_alerts(factory), timeout=3)
        assert [claim.event_id for claim in claims] == [second.id]
        await holder.rollback()
    later = await notifications._claim_alerts(factory)
    assert [claim.event_id for claim in later] == [first.id]

    async with factory() as db:
        ids = []
        for _ in range(8):
            *_, event = await seed(db)
            ids.append(event.id)
    a, b = await asyncio.gather(notifications._claim_alerts(factory), notifications._claim_alerts(factory))
    claimed = [claim.event_id for claim in [*a, *b]]
    assert len(claimed) == len(set(claimed)) == len(ids)
    assert set(claimed) == set(ids)


async def test_postgres_recovery_fences_stale_delivery_and_ack(pg_outbox, monkeypatch):
    _, factory, clock = pg_outbox
    async with factory() as db:
        *_, event = await seed(db)
    first = (await notifications._claim_alerts(factory))[0]
    clock[0] += notifications.OUTBOX_LEASE + timedelta(seconds=1)
    replacement = (await notifications._claim_alerts(factory))[0]
    contacted = []

    async def accept(*args, **kwargs):
        contacted.append(kwargs["event_id"])
        return True

    monkeypatch.setattr(notifications, "send_to_channel", accept)
    await notifications._deliver_claim(factory, first)
    assert contacted == []
    assert not await notifications._finish_claim(factory, first, success=True)
    await notifications._deliver_claim(factory, replacement)
    async with factory() as db:
        row = await db.get(AlertEvent, event.id)
        assert row.status == "sent" and row.attempt_count == 2
    assert contacted == [event.id]


async def test_postgres_to_real_transport_retry_preserves_webhook_identity_and_signed_bytes(pg_outbox, monkeypatch):
    """Real queue/claim/formatter/transport/ack; only HTTP wire and DNS are fixtures."""
    _, factory, clock = pg_outbox
    async with factory() as db:
        _, _, channel, event = await seed(db)
        channel.secret_token = "local-outbox-fixture"
        await db.commit()
    receipts = []

    async def public_dns(*args):
        return ["8.8.8.8"]

    async def wire(self, request):
        body = await request.aread()
        payload = json.loads(body)
        expected = hmac.new(b"local-outbox-fixture", body, hashlib.sha256).hexdigest()
        assert request.headers["X-Straz-Signature"] == "sha256=" + expected
        assert request.headers["Idempotency-Key"] == payload["event_id"] == str(event.id)
        receipts.append(payload["event_id"])
        return httpx.Response(503 if len(receipts) == 1 else 204, request=request)

    monkeypatch.setattr("app.services.safe_http.resolve_public_addresses", public_dns)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", wire)
    await notifications.process_alert_outbox({})
    async with factory() as db:
        row = await db.get(AlertEvent, event.id)
        assert row.status == "pending" and row.attempt_count == 1
        clock[0] = row.next_attempt_at
    await notifications.process_alert_outbox({})
    async with factory() as db:
        row = await db.get(AlertEvent, event.id)
        assert row.status == "sent" and row.attempt_count == 2
    assert receipts == [str(event.id), str(event.id)]


@pytest.mark.parametrize("source_revision", ["008_postgres_uuid_and_audit_fk", "009_cvss_and_poc_fields"])
async def test_postgres_upgrade_preserves_old_pending_processing_and_terminal_events(pg_database, source_revision):
    engine, _, url = pg_database

    async def migrate(target):
        result = await asyncio.to_thread(subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", target], cwd=API,
            env={**os.environ, "DATABASE_URL": url, "STRAZ_ENV": "test"}, capture_output=True)
        assert result.returncode == 0, "Migration failed (connection values suppressed)"

    await migrate(source_revision)
    org_id, channel_id = uuid.uuid4(), uuid.uuid4()
    ids = {status: uuid.uuid4() for status in ("pending", "processing", "sent", "failed")}
    async with engine.begin() as connection:
        await connection.execute(text("INSERT INTO organizations(id,name,slug) VALUES(:id,'Fixture','fixture')"), {"id": org_id})
        await connection.execute(text("INSERT INTO alert_channels(id,org_id,platform,name,destination_url) VALUES(:id,:org,'webhook','Fixture','https://example.invalid')"), {"id": channel_id, "org": org_id})
        for status, event_id in ids.items():
            await connection.execute(text("INSERT INTO alert_events(id,org_id,channel_id,event_type,severity,title,status) VALUES(:id,:org,:channel,'app.down','high','Preserved fixture',:status)"), {"id": event_id, "org": org_id, "channel": channel_id, "status": status})
    await migrate(REV10)
    await migrate(REV10)
    async with engine.connect() as connection:
        assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == REV10
        rows = (await connection.execute(text("SELECT id,status,title,attempt_count,next_attempt_at,lease_token,lease_expires_at FROM alert_events"))).all()
        assert len(rows) == 4
        assert {row.id: row.status for row in rows} == {event_id: status for status, event_id in ids.items()}
        assert all(row.title == "Preserved fixture" and row.attempt_count == 0 and row.next_attempt_at is None and row.lease_token is None and row.lease_expires_at is None for row in rows)
