import json
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Organization, OrganizationMember, OrgRole, User
from app.security import create_session_token, hash_password


@pytest.mark.asyncio
async def test_billing_plans_and_usage(client: AsyncClient, test_user: User):
    resp = await client.get("/api/billing/plans")
    assert resp.status_code == 200
    plans = resp.json()["plans"]
    assert "free" in plans
    assert "starter" in plans
    assert "pro" in plans
    assert "agency" in plans


@pytest.mark.asyncio
async def test_free_tier_app_limit_and_scan_quota(
    client: AsyncClient, db_session: AsyncSession
):
    settings = get_settings()

    # User on free tier
    user = User(
        id=uuid.uuid4(),
        email="freeuser@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Free Workspace",
        slug="free-workspace",
        plan_tier="free",
    )
    m = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=user.id, role=OrgRole.owner
    )
    db_session.add_all([user, org, m])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. First app succeeds
    app1_resp = await client.post(
        "/api/apps",
        headers={"X-Organization-Id": str(org.id)},
        json={"name": "First App", "base_url": "https://first.example.com"},
    )
    assert app1_resp.status_code == 201
    app1_id = app1_resp.json()["id"]

    # 2. Second app exceeds free limit (max 1 app) -> 402 Payment Required
    app2_resp = await client.post(
        "/api/apps",
        headers={"X-Organization-Id": str(org.id)},
        json={"name": "Second App", "base_url": "https://second.example.com"},
    )
    assert app2_resp.status_code == 402
    assert app2_resp.headers.get("x-upgrade-required") == "true"

    # 3. Disallowed profile on Free tier -> 402 Payment Required
    run_resp = await client.post(
        f"/api/apps/{app1_id}/runs",
        headers={"X-Organization-Id": str(org.id)},
        json={"profile": "safe"},
    )
    assert run_resp.status_code == 402
    assert "Vyžaduje sa upgrade" in run_resp.json()["detail"]


@pytest.mark.asyncio
async def test_checkout_and_webhook_upgrade(
    client: AsyncClient, db_session: AsyncSession
):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="upgrader@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Upgrade Org",
        slug="upgrade-org",
        plan_tier="free",
    )
    m = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=user.id, role=OrgRole.owner
    )
    db_session.add_all([user, org, m])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Create checkout session (simulation mode)
    checkout_resp = await client.post(
        "/api/billing/create-checkout-session",
        headers={"X-Organization-Id": str(org.id)},
        json={"tier": "pro"},
    )
    assert checkout_resp.status_code == 200
    assert "url" in checkout_resp.json()

    # 2. Webhook simulation payload for checkout.session.completed
    webhook_payload = {
        "id": f"evt_test_{uuid.uuid4().hex[:12]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(org.id),
                "customer": "cus_test_12345",
                "subscription": "sub_test_12345",
                "metadata": {"tier": "pro", "org_id": str(org.id)},
            }
        },
    }
    wh_resp = await client.post(
        "/api/billing/webhook",
        content=json.dumps(webhook_payload),
        headers={"Content-Type": "application/json"},
    )
    assert wh_resp.status_code == 200

    # 3. Check org usage - now Pro plan!
    usage_resp = await client.get("/api/billing/usage", headers={"X-Organization-Id": str(org.id)})
    assert usage_resp.status_code == 200
    assert usage_resp.json()["plan_tier"] == "pro"
    assert usage_resp.json()["apps_limit"] == 25
