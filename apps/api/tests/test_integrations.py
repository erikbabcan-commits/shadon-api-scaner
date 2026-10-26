import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Organization, OrganizationMember, OrgRole, User
from app.security import create_session_token, hash_password


@pytest.mark.asyncio
async def test_alert_channel_crud_and_plans(
    client: AsyncClient, db_session: AsyncSession
):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="alerts@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Alerting Org",
        slug="alert-org",
        plan_tier="free",
    )
    m = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=user.id, role=OrgRole.owner
    )
    db_session.add_all([user, org, m])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Free tier trying to add Slack -> 402 Payment Required
    slack_resp = await client.post(
        f"/api/orgs/{org.id}/channels",
        headers={"X-Organization-Id": str(org.id)},
        json={
            "platform": "slack",
            "name": "Team Slack",
            "destination_url": "https://hooks.slack.com/services/xxx/yyy/zzz",
        },
    )
    assert slack_resp.status_code == 402

    # 2. Free tier adding ntfy -> succeeds
    ntfy_resp = await client.post(
        f"/api/orgs/{org.id}/channels",
        headers={"X-Organization-Id": str(org.id)},
        json={
            "platform": "ntfy",
            "name": "Team ntfy",
            "destination_url": "https://ntfy.sh/my-topic",
        },
    )
    assert ntfy_resp.status_code == 201
    channel_id = ntfy_resp.json()["id"]

    # 3. Free tier trying to add 2nd channel -> 402 (limit 1)
    ch2_resp = await client.post(
        f"/api/orgs/{org.id}/channels",
        headers={"X-Organization-Id": str(org.id)},
        json={
            "platform": "ntfy",
            "name": "Second ntfy",
            "destination_url": "https://ntfy.sh/topic2",
        },
    )
    assert ch2_resp.status_code == 402

    # 4. List channels -> destination_url is masked
    list_resp = await client.get(
        f"/api/orgs/{org.id}/channels",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert list_resp.status_code == 200
    channels = list_resp.json()
    assert len(channels) == 1
    assert "https://ntfy.sh/***" in channels[0]["destination_url_masked"]

    # 5. Delete channel
    del_resp = await client.delete(
        f"/api/orgs/{org.id}/channels/{channel_id}",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_webhook_hmac_and_test_dispatch(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    async def delivered(*args, **kwargs):
        return True
    monkeypatch.setattr("app.routers.integrations.test_channel_delivery", delivered)
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="proalerts@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Pro Alert Org",
        slug="pro-alert-org",
        plan_tier="pro",
    )
    m = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=user.id, role=OrgRole.owner
    )
    db_session.add_all([user, org, m])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # Create signed webhook channel on Pro plan
    wh_resp = await client.post(
        f"/api/orgs/{org.id}/channels",
        headers={"X-Organization-Id": str(org.id)},
        json={
            "platform": "webhook",
            "name": "Custom Endpoint",
            "destination_url": "https://webhook.site/test-endpoint",
            "secret_token": "super_secret_webhook_signing_key_32c",
            "min_severity": "info",
        },
    )
    assert wh_resp.status_code == 201
    ch_id = wh_resp.json()["id"]

    # Trigger test endpoint
    test_resp = await client.post(
        f"/api/orgs/{org.id}/channels/{ch_id}/test",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert test_resp.status_code == 200
