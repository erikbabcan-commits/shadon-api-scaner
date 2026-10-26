"""Local negative tests. No real credentials, targets, Stripe or webhook calls."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select, func

from app.config import get_settings
from app.models import (App, AuditEvent, BillingEvent, Finding, FindingSeverity,
    FindingSource, Organization, OrganizationMember, OrgRole, RunStatus, ScanProfile,
    ScanRun, Target, TargetStatus)
from app.services.api_keys import create_api_key
from app.services.safe_http import validate_public_url


@pytest.fixture
async def context(db_session, test_user):
    member = await db_session.scalar(select(OrganizationMember).where(OrganizationMember.user_id == test_user.id))
    org = await db_session.get(Organization, member.org_id)
    org.plan_tier = "pro"
    app = App(id=uuid.uuid4(), organization_id=org.id, name="Local fixture", base_url="https://app.example.com")
    db_session.add(app)
    await db_session.flush()
    db_session.add(Target(app_id=app.id, host="app.example.com", status=TargetStatus.verified, verify_token="local-proof"))
    await db_session.commit()
    return org, member, app


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/orgs", None),
    ("POST", "/api/orgs", {"name": "forbidden"}),
    ("POST", "/api/apps", {"name": "forbidden", "base_url": "https://example.com"}),
    ("GET", "/api/findings", None),
    ("GET", "/api/auth/me", None),
    ("POST", "/api/auth/change-password", {"old_password": "x", "new_password": "new-password"}),
])
async def test_read_only_api_key_cannot_inherit_admin(client, db_session, test_user, context, method, path, body):
    org, _, _ = context
    _, raw = await create_api_key(db_session, org, test_user, "limited", ["apps:read"])
    await db_session.commit()
    response = await client.request(method, path, json=body, headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 403


async def test_scope_missing_and_expired_keys(client, db_session, test_user, context):
    org, _, _ = context
    key, raw = await create_api_key(db_session, org, test_user, "limited", [])
    await db_session.commit()
    assert (await client.get("/api/apps", headers={"Authorization": f"Bearer {raw}"})).status_code == 403
    key.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()
    assert (await client.get("/api/apps", headers={"Authorization": f"Bearer {raw}"})).status_code == 401
    assert (await client.get("/api/apps", headers={"Authorization": "Bearer straz_live_invalid"})).status_code == 401


async def test_key_loses_access_on_member_removal_or_plan_expiry(client, db_session, test_user, context):
    org, member, _ = context
    _, raw = await create_api_key(db_session, org, test_user, "limited", ["apps:read"])
    await db_session.commit()
    headers = {"Authorization": f"Bearer {raw}"}
    assert (await client.get("/api/apps", headers=headers)).status_code == 200
    org.subscription_status = "unpaid"
    await db_session.commit()
    assert (await client.get("/api/apps", headers=headers)).status_code == 402
    org.subscription_status = "active"
    await db_session.delete(member)
    await db_session.commit()
    assert (await client.get("/api/apps", headers=headers)).status_code == 403


@pytest.mark.parametrize("scopes,expires", [(["admin:*"], None), (["ci:scan"], "2000-01-01T00:00:00Z")])
async def test_key_input_validation(auth_client, context, scopes, expires):
    org, _, _ = context
    response = await auth_client.post(f"/api/orgs/{org.id}/api-keys", json={"name": "invalid", "scopes": scopes, "expires_at": expires})
    assert response.status_code == 422


async def test_tenant_orphans_and_other_tenants_are_invisible(auth_client, db_session, context):
    own_org, _, own_app = context
    foreign_org = Organization(id=uuid.uuid4(), name="Other tenant", slug="other-tenant")
    db_session.add(foreign_org)
    await db_session.flush()
    for org_id in (None, foreign_org.id):
        app = App(id=uuid.uuid4(), organization_id=org_id, name="Hidden", base_url="https://hidden.example.com")
        db_session.add(app)
        await db_session.flush()
        finding = Finding(app_id=app.id, title="Hidden finding", severity=FindingSeverity.critical, source=FindingSource.nuclei, fingerprint=uuid.uuid4().hex)
        run = ScanRun(app_id=app.id, profile=ScanProfile.safe)
        db_session.add_all([finding, run])
        await db_session.commit()
        for path in (f"/api/apps/{app.id}", f"/api/findings/{finding.id}", f"/api/runs/{run.id}", f"/api/apps/{app.id}/compliance", f"/api/apps/{app.id}/report/html"):
            assert (await auth_client.get(path)).status_code == 404
        assert (await auth_client.patch(f"/api/apps/{app.id}", json={"name": "attack"})).status_code == 404
        assert (await auth_client.delete(f"/api/apps/{app.id}")).status_code == 404
        assert (await auth_client.post("/api/ci/scan", json={"app_id": str(app.id), "wait": False})).status_code == 404
    assert [item["id"] for item in (await auth_client.get("/api/apps")).json()] == [str(own_app.id)]
    assert (await auth_client.get("/api/findings")).json() == []


async def test_viewer_cannot_trigger_manual_or_ci(auth_client, db_session, context):
    _, member, app = context
    member.role = OrgRole.viewer
    await db_session.commit()
    assert (await auth_client.post(f"/api/apps/{app.id}/runs", json={"profile": "heartbeat"})).status_code == 403
    assert (await auth_client.post("/api/ci/scan", json={"app_id": str(app.id), "wait": False})).status_code == 403


async def test_admin_cannot_promote_self_to_owner(auth_client, db_session, context, test_user):
    org, member, _ = context
    member.role = OrgRole.admin
    await db_session.commit()
    response = await auth_client.patch(f"/api/orgs/{org.id}/members/{test_user.id}", json={"role": "owner"})
    assert response.status_code == 403
    await db_session.refresh(member)
    assert member.role == OrgRole.admin


def sign(payload, secret=None):
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new((secret or get_settings().stripe_webhook_secret).encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={timestamp},v1={signature}", "Content-Type": "application/json"}


def checkout(org_id):
    return {"id": "evt_local_" + uuid.uuid4().hex, "type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": str(org_id), "mode": "subscription", "payment_status": "paid",
        "customer": "cus_local", "subscription": "sub_local", "metadata": {"tier": "pro"},
    }}}


async def test_stripe_unsigned_tampered_and_duplicate(client, db_session, context):
    org, _, _ = context
    org.plan_tier = "free"
    await db_session.commit()
    body, headers = sign(checkout(org.id))
    assert (await client.post("/api/billing/webhook", content=body)).status_code == 400
    assert (await client.post("/api/billing/webhook", content=body + b" ", headers=headers)).status_code == 400
    assert (await client.post("/api/billing/webhook", content=body, headers=headers)).status_code == 200
    assert (await client.post("/api/billing/webhook", content=body, headers=headers)).json()["status"] == "already_processed"
    assert (await db_session.scalar(select(func.count()).select_from(BillingEvent))) == 1
    await db_session.refresh(org)
    assert org.plan_tier == "pro"


async def test_stripe_disabled_without_secret(client, monkeypatch, context):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "")
    body, headers = sign(checkout(context[0].id), secret="local-secret")
    assert (await client.post("/api/billing/webhook", content=body, headers=headers)).status_code == 503


async def test_webhook_rolls_back_event_if_update_fails(client, db_session, context):
    event = checkout(context[0].id)
    event["data"]["object"]["metadata"]["tier"] = "invented-plan"
    body, headers = sign(event)
    response = await client.post("/api/billing/webhook", content=body, headers=headers)
    assert response.status_code == 400
    await db_session.rollback()
    assert await db_session.scalar(select(func.count()).select_from(BillingEvent)) == 0


async def test_production_csrf_allows_signed_webhook_not_cookie_bypass(client, monkeypatch, context):
    import app.main as main
    monkeypatch.setattr(main.settings, "straz_env", "production")
    body, headers = sign(checkout(context[0].id))
    # Production mock billing fails closed, but CSRF must not reject Stripe.
    assert (await client.post("/api/billing/webhook", content=body, headers=headers)).status_code == 503
    assert (await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}, headers={"Origin": "https://evil.example"})).status_code == 403


@pytest.mark.parametrize("url", ["https://10.0.0.1/hook", "https://[::1]/hook", "https://[::ffff:127.0.0.1]/", "https://169.254.169.254/", "file:///etc/passwd", "https://user:password@example.com/hook", "https://localhost./", "https://0.0.0.0/", "https://224.0.0.1/", "https://metadata.google.internal/"])
def test_ssrf_lexical_destinations(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


async def test_dns_mixed_public_private_is_rejected(monkeypatch):
    from app.services.safe_http import resolve_public_addresses
    async def answers(*args, **kwargs):
        return [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("127.0.0.1", 443))]
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
    with pytest.raises(ValueError):
        await resolve_public_addresses("webhook.example.com", 443)


async def test_dns_pin_sni_and_hmac_match_raw_utf8_body(monkeypatch):
    from app.services import safe_http
    from app.services.notifications.transport import send_to_channel
    from app.models import AlertChannel
    async def public(*args, **kwargs):
        return ["8.8.8.8"]
    async def wire(self, request):
        body = await request.aread()
        assert request.url.host == "8.8.8.8"
        assert request.headers["Host"] == "hooks.example.com"
        assert request.extensions["sni_hostname"] == "hooks.example.com"
        expected = hmac.new(b"local-shared-secret", body, hashlib.sha256).hexdigest()
        assert request.headers["X-Straz-Signature"] == "sha256=" + expected
        assert json.loads(request.content)["title"] == "Slovenský výpadok"
        return httpx.Response(200)
    monkeypatch.setattr(safe_http, "resolve_public_addresses", public)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", wire)
    channel = AlertChannel(id=uuid.uuid4(), platform="webhook", destination_url="https://hooks.example.com/path", secret_token="local-shared-secret")
    assert await send_to_channel(channel, "app.down", "high", "Slovenský výpadok", "detail", "local app")


async def test_domain_proof_cannot_use_unrelated_base_url(monkeypatch):
    from app.services import verify
    visited = []
    async def dns(*args):
        return False
    async def proof(url, token):
        visited.append(url)
        return "controlled.example.com" in url
    monkeypatch.setattr(verify, "verify_dns_txt", dns)
    monkeypatch.setattr(verify, "verify_well_known", proof)
    assert await verify.verify_target(host="victim.example.com", base_url="https://controlled.example.com", token="local-token", settings=get_settings()) is None
    assert all("controlled.example.com" not in url for url in visited)


async def test_ci_incomplete_never_passes_and_observations_are_run_specific(db_session, context):
    from app.services.ci import evaluate_ci_gate
    from app.services.findings import upsert_finding
    app = context[2]
    run = ScanRun(id=uuid.uuid4(), app_id=app.id, profile=ScanProfile.safe, status=RunStatus.done)
    db_session.add(run)
    await db_session.flush()
    assert (await evaluate_ci_gate(db_session, run))[0] is False
    run.observations_complete = True
    assert (await evaluate_ci_gate(db_session, run))[0] is True
    db_session.info["scan_run_id"] = run.id
    await upsert_finding(db_session, app_id=app.id, target_id=None, source=FindingSource.nuclei, severity=FindingSeverity.critical, title="Local critical fixture", detail=None, fingerprint="local-critical")
    await db_session.flush()
    passed, counts, _ = await evaluate_ci_gate(db_session, run)
    assert passed is False and counts["critical"] == 1 and counts["total_new"] == 1


@pytest.mark.usefixtures("allow_cli_profiles")
async def test_ci_queue_failure_is_not_accepted(auth_client, db_session, context, monkeypatch):
    async def unavailable(*args):
        raise OSError("queue offline")
    monkeypatch.setattr("app.routers.ci.get_arq_redis", unavailable)
    response = await auth_client.post("/api/ci/scan", json={"app_id": str(context[2].id), "wait": False})
    assert response.status_code == 503
    assert await db_session.scalar(select(ScanRun.status)) == RunStatus.failed


async def test_real_mutation_writes_tenant_actor_and_redacts(auth_client, db_session, context, test_user):
    response = await auth_client.patch(f"/api/apps/{context[2].id}", json={"name": "Renamed"}, headers={"User-Agent": "Local regression", "X-Forwarded-For": "203.0.113.123"})
    assert response.status_code == 200
    event = await db_session.scalar(select(AuditEvent).where(AuditEvent.action == "app.update"))
    assert event.organization_id == context[0].id
    assert event.actor_email == test_user.email
    assert event.ip_address != "203.0.113.123" and event.ip_address is not None
    from app.services.audit import sanitize_audit_details
    assert "private/path" not in sanitize_audit_details("https://hooks.example.com/private/path?token=private")
    assert "local-bearer-value" not in sanitize_audit_details("Bearer local-bearer-value")


@pytest.mark.parametrize("text", ["=SUM(1)", "  +SUM(1)", "\t=1", "\r@SUM(1)", "\ufeff-1"])
def test_csv_formula_whitespace(text):
    from app.routers.audit import sanitize_csv_cell
    assert sanitize_csv_cell(text).startswith("'")


@pytest.mark.parametrize("endpoint", ["/healthz/readiness", "/api/health", "/api/health/ready"])
async def test_readiness_requires_redis_and_no_exception_leaks(client, monkeypatch, endpoint):
    async def up(*args):
        return True, 0.3, None
    async def down(*args):
        return False, 0.5, "Redis unavailable"
    monkeypatch.setattr("app.routers.health.check_database_latency", up)
    monkeypatch.setattr("app.routers.health.check_redis_latency", down)
    response = await client.get(endpoint)
    assert response.status_code == 503 and response.json()["ready"] is False
    assert response.json()["checks"]["redis"]["latency_ms"] == 0.5
    from app.services.health import check_database_latency
    class FailingDB:
        async def execute(self, statement):
            raise RuntimeError("postgresql://private-credentials@internal-host")
    ok, _, error = await check_database_latency(FailingDB())
    assert ok is False and "private-credentials" not in error


async def test_validation_errors_do_not_echo_secrets(client):
    response = await client.post("/api/auth/register", json={"email": "invalid", "password": "should-never-be-echoed"})
    assert response.status_code == 422 and "should-never-be-echoed" not in response.text


async def test_branding_disallows_injection(auth_client, context):
    org = context[0]
    for body in ({"custom_logo_url": "javascript:alert(1)"}, {"brand_color": "#x;y{}z"}):
        assert (await auth_client.patch(f"/api/orgs/{org.id}/branding", json=body)).status_code == 422


@pytest.mark.parametrize("critical", [False, True])
@pytest.mark.usefixtures("allow_cli_profiles")
async def test_ci_wait_true_clean_and_critical(auth_client, db_session, context, monkeypatch, critical):
    from app.services.findings import upsert_finding
    class CompletedQueue:
        async def enqueue_job(self, name, run_id):
            run = await db_session.get(ScanRun, uuid.UUID(run_id))
            db_session.info["scan_run_id"] = run.id
            if critical:
                await upsert_finding(db_session, app_id=run.app_id, target_id=None, source=FindingSource.nuclei,
                    severity=FindingSeverity.critical, title="Local fixture", detail=None, fingerprint="ci-fixture")
            run.status = RunStatus.done
            run.observations_complete = True
            await db_session.commit()
            return object()
    async def queue(*args):
        return CompletedQueue()
    monkeypatch.setattr("app.routers.ci.get_arq_redis", queue)
    response = await auth_client.post("/api/ci/scan", json={"app_id": str(context[2].id), "wait": True, "timeout_seconds": 2})
    assert response.status_code == (424 if critical else 200)
    assert response.json()["passed"] is (not critical)


def test_malformed_scanner_output_cannot_pass_ci():
    from app.services.scanners import _parse_trivy_json
    for output in ("", "not-json", "{}"):
        with pytest.raises(RuntimeError):
            _parse_trivy_json(output, "", 0, "local-fixture")


async def test_notifications_are_transactional_without_network(db_session, context, monkeypatch):
    from app.models import AlertChannel, AlertEvent
    from app.services.notifications import dispatch_alert
    org, _, app = context
    db_session.add(AlertChannel(org_id=org.id, platform="webhook", name="Local fixture", destination_url="https://hooks.example.com", events='["finding.created"]', min_severity="critical"))
    await db_session.commit()
    await dispatch_alert(db_session, org.id, "finding.created", "medium", "Local fixture", app=app)
    assert await db_session.scalar(select(func.count()).select_from(AlertEvent)) == 0
    await dispatch_alert(db_session, org.id, "finding.created", "critical", "Local fixture", app=app)
    assert await db_session.scalar(select(func.count()).select_from(AlertEvent)) == 1
    await db_session.rollback()
    assert await db_session.scalar(select(func.count()).select_from(AlertEvent)) == 0


def test_missing_scan_coverage_does_not_claim_compliance():
    from app.services.compliance import evaluate_nis2_areas
    assert all(area["status"] == "WARNING" for area in evaluate_nis2_areas([]))


async def test_audit_orm_rejects_mutation(db_session, context):
    from app.services.audit import write_audit_log
    event = await write_audit_log(db_session, org_id=context[0].id, action="local.fixture")
    await db_session.commit()
    event.detail = "tampered"
    with pytest.raises(ValueError, match="immutable"):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.parametrize("scanner_fails", [False, True])
async def test_worker_marks_observations_complete_only_after_success(db_session, context, monkeypatch, scanner_fails):
    from contextlib import asynccontextmanager
    from app import worker
    from app.services.findings import upsert_finding
    org, _, app = context
    run = ScanRun(id=uuid.uuid4(), app_id=app.id, profile=ScanProfile.heartbeat, status=RunStatus.queued)
    db_session.add(run)
    await db_session.commit()
    run_id = run.id
    @asynccontextmanager
    async def sessions():
        yield db_session
    async def public(*args):
        return ["8.8.8.8"]
    async def scanner(db, application):
        if scanner_fails:
            raise RuntimeError("Synthetic scanner failure")
        await upsert_finding(db, app_id=application.id, target_id=None, source=FindingSource.heartbeat,
            severity=FindingSeverity.critical, title="Local fixture", detail=None, fingerprint="worker-fixture")
    async def no_cache(*args):
        return None
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "resolve_public_addresses", public)
    monkeypatch.setattr(worker, "_heartbeat", scanner)
    monkeypatch.setattr(worker, "_invalidate_overview_cache", no_cache)
    await worker.execute_scan_run({"redis": object()}, str(run_id))
    refreshed = await db_session.get(ScanRun, run_id)
    assert refreshed.status == (RunStatus.failed if scanner_fails else RunStatus.done)
    assert refreshed.observations_complete is (not scanner_fails)


async def test_modern_invoice_failure_matches_exact_subscription(client, db_session, context):
    org = context[0]
    org.stripe_customer_id = "cus_local"
    org.stripe_subscription_id = "sub_local"
    await db_session.commit()
    event = {"id": "evt_local_invoice", "type": "invoice.payment_failed", "data": {"object": {
        "customer": "cus_local", "parent": {"subscription_details": {"subscription": "sub_local"}}
    }}}
    body, headers = sign(event)
    assert (await client.post("/api/billing/webhook", content=body, headers=headers)).status_code == 200
    await db_session.refresh(org)
    assert org.subscription_status == "past_due" and org.plan_tier == "free"


@pytest.mark.parametrize("platform", ["slack", "discord", "teams", "ntfy"])
async def test_platform_payload_delivery_and_unicode_headers(monkeypatch, platform):
    from app.services import safe_http
    from app.services.notifications.transport import send_to_channel
    from app.models import AlertChannel
    async def public(*args):
        return ["8.8.8.8"]
    async def wire(self, request):
        body = await request.aread()
        if platform == "ntfy":
            from email.header import decode_header
            value, charset = decode_header(request.headers["Title"])[0]
            assert value.decode(charset) == "Stráž: Výpadok"
            assert request.headers["Priority"] == "5"
        else:
            payload = json.loads(body)
            assert {"slack": "attachments", "discord": "embeds", "teams": "attachments"}[platform] in payload
        return httpx.Response(200)
    monkeypatch.setattr(safe_http, "resolve_public_addresses", public)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", wire)
    channel = AlertChannel(id=uuid.uuid4(), platform=platform, destination_url="https://hooks.example.com/path")
    assert await send_to_channel(channel, "app.down", "critical", "Výpadok", "Local fixture", "Local app")
