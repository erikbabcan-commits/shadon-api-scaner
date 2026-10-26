import uuid

import pytest
from sqlalchemy import select

from app.models import (
    App, CLI_SCANNER_PROFILES, CLI_SCANNER_UNAVAILABLE,
    OrganizationMember, ScanProfile, ScanRun,
)


@pytest.mark.parametrize('profile', sorted(CLI_SCANNER_PROFILES, key=lambda p: p.value))
async def test_run_api_rejects_cli_profile(auth_client, db_session, test_user, profile):
    org_id = await db_session.scalar(
        select(OrganizationMember.org_id).where(OrganizationMember.user_id == test_user.id)
    )
    app = App(id=uuid.uuid4(), organization_id=org_id, name='Local fixture', base_url='https://example.invalid')
    db_session.add(app)
    await db_session.commit()
    response = await auth_client.post(f'/api/apps/{app.id}/runs', json={'profile': profile.value})
    assert response.status_code == 409
    assert response.json()['detail'] == CLI_SCANNER_UNAVAILABLE
    assert await db_session.scalar(select(ScanRun).where(ScanRun.app_id == app.id)) is None


def test_python_profiles_remain_available():
    assert ScanProfile.heartbeat not in CLI_SCANNER_PROFILES
    assert ScanProfile.internetdb not in CLI_SCANNER_PROFILES
    assert len(CLI_SCANNER_PROFILES) == 8
