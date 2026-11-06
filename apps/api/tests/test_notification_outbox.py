"""Durable outbox behavior with local DB fixtures and no external delivery."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.db import Base

from app.models import AlertChannel, AlertEvent, App, Organization
from app.services import notifications
from app.services.notifications.formatters import format_webhook


NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def outbox(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    clock = [NOW]
    monkeypatch.setattr(notifications, "_utcnow", lambda: clock[0])
    try:
        yield factory, clock
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def outbox_db(outbox):
    async with outbox[0]() as db:
        yield db


async def seed(db, *, status="pending", attempts=0, lease=None, expiry=None, ready=None, created=None):
    org = Organization(id=uuid.uuid4(), name="Local outbox fixture", slug=uuid.uuid4().hex)
    db.add(org)
    await db.flush()
    app = App(id=uuid.uuid4(), organization_id=org.id, name="Local app", base_url="https://example.invalid")
    channel = AlertChannel(id=uuid.uuid4(), org_id=org.id, platform="webhook", name="Local channel",
                           destination_url="https://example.invalid/notify", events='["all"]')
    db.add_all([app, channel])
    await db.flush()
    event = AlertEvent(id=uuid.uuid4(), org_id=org.id, app_id=app.id, channel_id=channel.id,
                       event_type="finding.created", severity="high", title="Synthetic alert",
                       status=status, created_at=created or NOW, attempt_count=attempts,
                       lease_token=lease, lease_expires_at=expiry, next_attempt_at=ready)
    db.add(event)
    await db.commit()
    return org, app, channel, event


async def state(factory, event_id):
    async with factory() as db:
        return await db.get(AlertEvent, event_id)


async def test_successful_delivery_is_acknowledged_and_not_repeated(outbox_db, outbox, monkeypatch):
    factory, _ = outbox
    _, _, _, event = await seed(outbox_db)
    sent = []

    async def deliver(*args, **kwargs):
        sent.append(kwargs["event_id"])
        return True

    monkeypatch.setattr(notifications, "send_to_channel", deliver)
    await notifications.process_alert_outbox({})
    await notifications.process_alert_outbox({})
    row = await state(factory, event.id)
    assert row.status == "sent" and row.attempt_count == 1
    assert row.processed_at is not None
    assert row.lease_token is None and row.lease_expires_at is None and row.next_attempt_at is None
    assert sent == [event.id]


async def test_one_transport_exception_does_not_strand_batch_and_retry_keeps_event_id(outbox_db, outbox, monkeypatch, caplog):
    factory, clock = outbox
    *_, first = await seed(outbox_db)
    *_, second = await seed(outbox_db)
    attempts = []

    async def deliver(*args, event_id=None, **kwargs):
        attempts.append(event_id)
        if event_id == first.id and attempts.count(first.id) == 1:
            raise RuntimeError("Synthetic transport exception must not be logged verbatim")
        return True

    monkeypatch.setattr(notifications, "send_to_channel", deliver)
    await notifications.process_alert_outbox({})
    a, b = await state(factory, first.id), await state(factory, second.id)
    assert a.status == "pending" and a.attempt_count == 1 and a.processed_at is None
    assert notifications._aware(a.next_attempt_at) == NOW + timedelta(seconds=30)
    assert b.status == "sent"
    await notifications.process_alert_outbox({})
    assert attempts.count(first.id) == 1
    clock[0] += timedelta(seconds=30)
    await notifications.process_alert_outbox({})
    assert (await state(factory, first.id)).status == "sent"
    assert attempts.count(first.id) == 2 and attempts.count(second.id) == 1
    assert "Synthetic transport exception must not be logged verbatim" not in caplog.text


async def test_hanging_destination_times_out_without_losing_other_delivery(outbox_db, outbox, monkeypatch):
    import asyncio
    factory, _ = outbox
    *_, slow = await seed(outbox_db)
    *_, fast = await seed(outbox_db)
    monkeypatch.setattr(notifications, "OUTBOX_DELIVERY_TIMEOUT_SECONDS", 0.01)

    async def deliver(*args, event_id=None, **kwargs):
        if event_id == slow.id:
            await asyncio.sleep(10)
        return True

    monkeypatch.setattr(notifications, "send_to_channel", deliver)
    await asyncio.wait_for(notifications.process_alert_outbox({}), timeout=2)
    assert (await state(factory, slow.id)).status == "pending"
    assert (await state(factory, fast.id)).status == "sent"


async def test_crash_after_receiver_accepts_may_repeat_same_event_without_false_exactly_once_claim(outbox_db, outbox, monkeypatch):
    import asyncio
    factory, clock = outbox
    *_, event = await seed(outbox_db)
    receipts = []

    async def receiver(*args, **kwargs):
        receipts.append(kwargs["event_id"])
        return True

    original_finish = notifications._finish_claim

    async def crash(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(notifications, "send_to_channel", receiver)
    monkeypatch.setattr(notifications, "_finish_claim", crash)
    with pytest.raises(asyncio.CancelledError):
        await notifications.process_alert_outbox({})
    assert receipts == [event.id]
    clock[0] += notifications.OUTBOX_LEASE + timedelta(seconds=1)
    monkeypatch.setattr(notifications, "_finish_claim", original_finish)
    await notifications.process_alert_outbox({})
    assert receipts == [event.id, event.id]
    assert (await state(factory, event.id)).status == "sent"


async def test_repeated_failure_uses_durable_backoff_then_stops(outbox_db, outbox, monkeypatch):
    factory, clock = outbox
    *_, event = await seed(outbox_db)
    calls = []

    async def fail(*args, **kwargs):
        calls.append(kwargs["event_id"])
        return False

    monkeypatch.setattr(notifications, "send_to_channel", fail)
    for attempt in range(1, notifications.OUTBOX_MAX_ATTEMPTS + 1):
        await notifications.process_alert_outbox({})
        row = await state(factory, event.id)
        assert row.attempt_count == attempt
        if attempt < notifications.OUTBOX_MAX_ATTEMPTS:
            assert row.status == "pending" and row.processed_at is None
            expected = min(900, 30 * 2 ** (attempt - 1))
            assert notifications._aware(row.next_attempt_at) == clock[0] + timedelta(seconds=expected)
            await notifications.process_alert_outbox({})
            assert len(calls) == attempt
            clock[0] = notifications._aware(row.next_attempt_at)
        else:
            assert row.status == "failed" and row.processed_at is not None
            assert row.next_attempt_at is None
    clock[0] += timedelta(days=1)
    await notifications.process_alert_outbox({})
    assert len(calls) == notifications.OUTBOX_MAX_ATTEMPTS


async def test_crashed_claim_is_recovered_and_old_worker_cannot_ack_new_claim(outbox_db, outbox):
    factory, clock = outbox
    *_, event = await seed(outbox_db)
    old = (await notifications._claim_alerts(factory))[0]
    assert await notifications._claim_alerts(factory) == []
    clock[0] += notifications.OUTBOX_LEASE + timedelta(seconds=1)
    # Even before a replacement claim, an expired worker cannot acknowledge.
    assert not await notifications._finish_claim(factory, old, success=True)
    replacement = (await notifications._claim_alerts(factory))[0]
    assert replacement.token != old.token and replacement.attempt == old.attempt + 1
    assert not await notifications._finish_claim(factory, old, success=False)
    assert await notifications._finish_claim(factory, replacement, success=True)
    row = await state(factory, event.id)
    assert row.status == "sent" and row.attempt_count == 2


async def test_cancelled_delivery_leaves_recoverable_lease(outbox_db, outbox, monkeypatch):
    import asyncio
    factory, clock = outbox
    *_, event = await seed(outbox_db)

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(notifications, "send_to_channel", cancel)
    with pytest.raises(asyncio.CancelledError):
        await notifications.process_alert_outbox({})
    assert (await state(factory, event.id)).status == "processing"
    clock[0] += notifications.OUTBOX_LEASE + timedelta(seconds=1)

    async def success(*args, **kwargs):
        return True

    monkeypatch.setattr(notifications, "send_to_channel", success)
    await notifications.process_alert_outbox({})
    row = await state(factory, event.id)
    assert row.status == "sent" and row.attempt_count == 2


@pytest.mark.parametrize("kind", ["disabled", "tenant", "app-tenant", "app-scope", "unsubscribed", "severity", "malformed-events"])
async def test_invalid_or_revoked_destination_never_receives_queued_alert(outbox_db, outbox, monkeypatch, kind):
    factory, _ = outbox
    _, app, channel, event = await seed(outbox_db)
    if kind == "disabled":
        channel.is_active = False
    elif kind in {"tenant", "app-tenant"}:
        other = Organization(id=uuid.uuid4(), name="Other tenant", slug=uuid.uuid4().hex)
        outbox_db.add(other)
        if kind == "tenant":
            channel.org_id = other.id
        else:
            app.organization_id = other.id
    elif kind == "app-scope":
        other_app = App(id=uuid.uuid4(), organization_id=app.organization_id, name="Other app", base_url="https://example.invalid")
        outbox_db.add(other_app)
        channel.app_id = other_app.id
    elif kind == "unsubscribed":
        channel.events = '["app.down"]'
    elif kind == "severity":
        channel.min_severity = "critical"
    else:
        channel.events = '{malformed'
    await outbox_db.commit()

    async def never(*args, **kwargs):
        pytest.fail("Revoked/mismatched channel received an alert")

    monkeypatch.setattr(notifications, "send_to_channel", never)
    await notifications.process_alert_outbox({})
    row = await state(factory, event.id)
    assert row.status == "failed" and row.processed_at is not None
    assert row.attempt_count == 0


async def test_channel_disabled_after_claim_is_rechecked_before_delivery(outbox_db, outbox, monkeypatch):
    factory, _ = outbox
    _, _, channel, event = await seed(outbox_db)
    claim = (await notifications._claim_alerts(factory))[0]
    channel.is_active = False
    await outbox_db.commit()

    async def never(*args, **kwargs):
        pytest.fail("Channel disabled while waiting was still contacted")

    monkeypatch.setattr(notifications, "send_to_channel", never)
    await notifications._deliver_claim(factory, claim)
    assert (await state(factory, event.id)).status == "failed"


@pytest.mark.parametrize("status,attempts,expiry,created,expected", [
    ("processing", 0, None, NOW, "sent"),
    ("processing", 5, NOW - timedelta(seconds=1), NOW, "failed"),
    ("pending", 0, None, NOW - timedelta(days=2), "failed"),
    ("failed", 1, None, NOW, "failed"),
    ("sent", 1, None, NOW, "sent"),
])
async def test_legacy_claim_recovery_does_not_retry_historical_terminal_rows(outbox_db, outbox, monkeypatch, status, attempts, expiry, created, expected):
    factory, _ = outbox
    *_, event = await seed(outbox_db, status=status, attempts=attempts, expiry=expiry, created=created)
    calls = []

    async def deliver(*args, **kwargs):
        calls.append(kwargs["event_id"])
        return True

    monkeypatch.setattr(notifications, "send_to_channel", deliver)
    await notifications.process_alert_outbox({})
    assert (await state(factory, event.id)).status == expected
    assert calls == ([event.id] if status == "processing" and attempts == 0 else [])


def test_webhook_identifies_distinct_events_and_retains_retry_identity():
    channel = AlertChannel(id=uuid.uuid4(), secret_token="synthetic-local-hmac-key")
    first, second = uuid.uuid4(), uuid.uuid4()
    a, headers = format_webhook(channel, "app.down", "high", "Fixture", None, None, event_id=first)
    retry, _ = format_webhook(channel, "app.down", "high", "Fixture", None, None, event_id=first)
    b, _ = format_webhook(channel, "app.down", "high", "Fixture", None, None, event_id=second)
    assert a["event_id"] == retry["event_id"] == headers["Idempotency-Key"] == str(first)
    assert b["event_id"] == str(second) != a["event_id"] != str(channel.id)
