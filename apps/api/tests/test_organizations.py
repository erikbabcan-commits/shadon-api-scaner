import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import App, Organization, OrganizationMember, OrgRole, User
from app.security import create_session_token, hash_password


@pytest.mark.asyncio
async def test_organization_crud_and_isolation(
    client: AsyncClient, db_session: AsyncSession, test_user: User
):
    settings = get_settings()

    # 1. User 1 has default org from fixture
    token1 = create_session_token(settings, str(test_user.id), test_user.token_version)
    client.cookies.set(settings.straz_cookie_name, token1)

    resp = await client.get("/api/orgs")
    assert resp.status_code == 200
    orgs = resp.json()
    assert len(orgs) >= 1
    org1_id = orgs[0]["id"]
    assert orgs[0]["role"] == "owner"

    # Create app in Org 1
    app_resp = await client.post(
        "/api/apps",
        headers={"X-Organization-Id": org1_id},
        json={"name": "Org 1 App", "base_url": "https://org1.example.com"},
    )
    assert app_resp.status_code == 201
    app1_id = app_resp.json()["id"]

    # 2. Create User 2 with their own Org 2
    user2 = User(
        id=uuid.uuid4(),
        email="user2@example.com",
        password_hash=hash_password("Pass12345!"),
        token_version=1,
    )
    org2 = Organization(id=uuid.uuid4(), name="Org 2", slug="org-2")
    m2 = OrganizationMember(
        id=uuid.uuid4(), org_id=org2.id, user_id=user2.id, role=OrgRole.owner
    )
    db_session.add_all([user2, org2, m2])
    await db_session.commit()

    # Authenticate as User 2
    token2 = create_session_token(settings, str(user2.id), user2.token_version)
    client.cookies.set(settings.straz_cookie_name, token2)

    # User 2 cannot see Org 1 apps
    list_resp = await client.get("/api/apps", headers={"X-Organization-Id": str(org2.id)})
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0

    # User 2 cannot access Org 1 app by ID
    get_resp = await client.get(f"/api/apps/{app1_id}", headers={"X-Organization-Id": str(org2.id)})
    assert get_resp.status_code == 404

    # User 2 cannot spoof X-Organization-Id to Org 1
    spoof_resp = await client.get("/api/apps", headers={"X-Organization-Id": org1_id})
    assert spoof_resp.status_code == 403


@pytest.mark.asyncio
async def test_organization_rbac_roles(
    client: AsyncClient, db_session: AsyncSession
):
    settings = get_settings()

    # Create Org with Owner, Member, and Viewer
    owner = User(id=uuid.uuid4(), email="owner@test.com", password_hash=hash_password("Pass!123"), token_version=1)
    viewer = User(id=uuid.uuid4(), email="viewer@test.com", password_hash=hash_password("Pass!123"), token_version=1)
    org = Organization(id=uuid.uuid4(), name="RBAC Test Org", slug="rbac-test")

    m_owner = OrganizationMember(id=uuid.uuid4(), org_id=org.id, user_id=owner.id, role=OrgRole.owner)
    m_viewer = OrganizationMember(id=uuid.uuid4(), org_id=org.id, user_id=viewer.id, role=OrgRole.viewer)
    db_session.add_all([owner, viewer, org, m_owner, m_viewer])
    await db_session.commit()

    # 1. Viewer role checks
    v_token = create_session_token(settings, str(viewer.id), viewer.token_version)
    client.cookies.set(settings.straz_cookie_name, v_token)

    # Viewer CAN read apps
    v_apps = await client.get("/api/apps", headers={"X-Organization-Id": str(org.id)})
    assert v_apps.status_code == 200

    # Viewer CANNOT create app (requires member) -> 403
    v_create = await client.post(
        "/api/apps",
        headers={"X-Organization-Id": str(org.id)},
        json={"name": "Viewer Bad App", "base_url": "https://bad.example.com"},
    )
    assert v_create.status_code == 403

    # Viewer CANNOT invite members -> 403
    v_invite = await client.post(
        f"/api/orgs/{org.id}/invitations",
        headers={"X-Organization-Id": str(org.id)},
        json={"email": "new@test.com", "role": "member"},
    )
    assert v_invite.status_code == 403

    # 2. Owner can invite
    o_token = create_session_token(settings, str(owner.id), owner.token_version)
    client.cookies.set(settings.straz_cookie_name, o_token)

    invite_resp = await client.post(
        f"/api/orgs/{org.id}/invitations",
        headers={"X-Organization-Id": str(org.id)},
        json={"email": "invitee@test.com", "role": "member"},
    )
    assert invite_resp.status_code == 201
    invite_data = invite_resp.json()
    token = invite_data["token"]

    # Invitee creates user account and accepts
    invitee = User(id=uuid.uuid4(), email="invitee@test.com", password_hash=hash_password("Pass!123"), token_version=1)
    db_session.add(invitee)
    await db_session.commit()

    i_token = create_session_token(settings, str(invitee.id), invitee.token_version)
    client.cookies.set(settings.straz_cookie_name, i_token)

    accept_resp = await client.post(f"/api/invitations/{token}/accept")
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "accepted"
