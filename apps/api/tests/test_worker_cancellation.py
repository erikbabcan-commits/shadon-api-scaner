import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import worker
from app.models import App, Organization, RunStatus, ScanProfile, ScanRun


async def seed(db, monkeypatch):
    org = Organization(id=uuid.uuid4(), name='Cancellation fixture', slug=uuid.uuid4().hex)
    app = App(id=uuid.uuid4(), organization_id=org.id, name='Original fixture', base_url='https://example.invalid')
    run = ScanRun(id=uuid.uuid4(), app_id=app.id, profile=ScanProfile.heartbeat, status=RunStatus.queued)
    db.add_all([org, app, run])
    await db.commit()
    monkeypatch.setattr(worker, 'SessionLocal', async_sessionmaker(db.bind, expire_on_commit=False))
    return app.id, run.id


async def test_cancel_rolls_back_partial_observations_and_marks_failed(db_session, monkeypatch):
    app_id, run_id = await seed(db_session, monkeypatch)
    started = asyncio.Event()
    async def heartbeat(db, app):
        app.name = 'Uncommitted partial fixture'
        await db.flush()
        started.set()
        await asyncio.Future()
    monkeypatch.setattr(worker, '_heartbeat', heartbeat)
    task = asyncio.create_task(worker.execute_scan_run({'redis': object()}, str(run_id)))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    db_session.expire_all()
    run = await db_session.get(ScanRun, run_id)
    assert run.status == RunStatus.failed and not run.observations_complete
    assert run.finished_at is not None
    assert (await db_session.get(App, app_id)).name == 'Original fixture'


@pytest.mark.parametrize('cancel', [False, True])
async def test_failure_after_result_commit_preserves_completed_scan(db_session, monkeypatch, cancel):
    _, run_id = await seed(db_session, monkeypatch)
    reached_cache = asyncio.Event()
    async def heartbeat(*args):
        pass
    async def cache(*args):
        reached_cache.set()
        if cancel:
            await asyncio.Future()
        raise RuntimeError('Synthetic cache outage')
    monkeypatch.setattr(worker, '_heartbeat', heartbeat)
    monkeypatch.setattr(worker, '_invalidate_overview_cache', cache)
    task = asyncio.create_task(worker.execute_scan_run({'redis': object()}, str(run_id)))
    await asyncio.wait_for(reached_cache.wait(), 2)
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
    else:
        await asyncio.wait_for(task, 2)
    db_session.expire_all()
    run = await db_session.get(ScanRun, run_id)
    assert run.status == RunStatus.done and run.observations_complete


async def test_repeated_cancellation_waits_for_database_cleanup(db_session, monkeypatch):
    _, run_id = await seed(db_session, monkeypatch)
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = worker._fail_unfinished_run
    async def heartbeat(*args):
        started.set()
        await asyncio.Future()
    async def cleanup(*args):
        cleaning.set()
        await release.wait()
        await original(*args)
    monkeypatch.setattr(worker, '_heartbeat', heartbeat)
    monkeypatch.setattr(worker, '_fail_unfinished_run', cleanup)
    task = asyncio.create_task(worker.execute_scan_run({'redis': object()}, str(run_id)))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        if not task.done():
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
    db_session.expire_all()
    assert (await db_session.get(ScanRun, run_id)).status == RunStatus.failed


async def test_old_attempt_cleanup_preserves_newer_running_attempt(db_session, monkeypatch):
    _, run_id = await seed(db_session, monkeypatch)
    first_start = datetime.now(timezone.utc) - timedelta(minutes=1)
    run = await db_session.get(ScanRun, run_id)
    run.status = RunStatus.running
    run.started_at = first_start + timedelta(seconds=1)
    await db_session.commit()

    await worker._fail_unfinished_run(db_session, run_id, first_start, 'Old attempt failed')

    db_session.expire_all()
    current = await db_session.get(ScanRun, run_id)
    assert current.status == RunStatus.running
    assert current.error is None and current.finished_at is None
