import pytest
from sqlalchemy import func, select
from app.models import App, AuditEvent, Finding, ScanRun, Target, TargetStatus
from app.services.demo import seed_demo


@pytest.mark.asyncio
async def test_demo_is_idempotent_and_never_scans(db_session, test_user):
    expected = {"apps": 3, "findings": 10, "runs": 5, "audit_examples": 10}
    assert await seed_demo(db_session, test_user) == expected
    await db_session.commit()
    assert await seed_demo(db_session, test_user) == expected
    await db_session.commit()
    for model, count in ((App, 3), (Finding, 10), (ScanRun, 5), (AuditEvent, 10)):
        assert await db_session.scalar(select(func.count()).select_from(model)) == count
    apps = list(await db_session.scalars(select(App)))
    assert all(not any((app.heartbeat_enabled, app.safe_enabled, app.tls_enabled, app.ports_enabled,
        app.trivy_enabled, app.gitleaks_enabled, app.http_enabled, app.internetdb_enabled,
        app.subdomain_enabled)) for app in apps)
    assert all(target.status == TargetStatus.pending for target in await db_session.scalars(select(Target)))
    assert all(not run.observations_complete for run in await db_session.scalars(select(ScanRun)))
