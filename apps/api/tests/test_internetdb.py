"""InternetDB fixtures only: no external DNS, HTTP, credentials or scan traffic."""
from __future__ import annotations

import copy
import json
import uuid

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models import (
    App, Finding, FindingSeverity, FindingSource, FindingStatus,
    OrganizationMember, RunStatus, ScanRun, ScanRunFinding, Target, TargetStatus,
)
from app.services.internetdb import fetch_internetdb


IP = "8.8.8.8"
HOST = {"ip": IP, "ports": [443], "cpes": [], "hostnames": [], "tags": [], "vulns": ["CVE-2026-0001"]}


class FixtureRedis:
    def __init__(self, cached=None):
        self.cached = cached
        self.writes = []

    async def get(self, key):
        return self.cached

    async def set(self, key, value, **kwargs):
        self.writes.append((key, value))
        return True


def fixture_http(monkeypatch, *, status=200, body=None, raw=None, timeout=False):
    requests = []

    async def wire(self, request):
        requests.append(request)
        if timeout:
            raise httpx.ReadTimeout("Synthetic upstream timeout", request=request)
        if raw is not None:
            return httpx.Response(status, content=raw, request=request)
        return httpx.Response(status, json=body, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", wire)
    return requests


@pytest.mark.parametrize("case", ["timeout", "429", "503", "malformed", "array", "missing-fields", "wrong-ip", "null-vulns", "string-ports", "404-html"])
async def test_incomplete_provider_response_never_becomes_empty_or_low_findings(monkeypatch, case):
    body = copy.deepcopy(HOST)
    options = {"body": body}
    if case == "timeout":
        options["timeout"] = True
    elif case in {"429", "503"}:
        options.update(status=int(case), body={"detail": "Unavailable"})
    elif case == "malformed":
        options["raw"] = b"not-json"
    elif case == "array":
        options["body"] = []
    elif case == "missing-fields":
        options["body"] = {"ip": IP}
    elif case == "wrong-ip":
        body["ip"] = "1.1.1.1"
    elif case == "null-vulns":
        body["vulns"] = None
    elif case == "string-ports":
        body["ports"] = "443"
    elif case == "404-html":
        options.update(status=404, raw=b"<h1>Proxy route not found</h1>")
    fixture_http(monkeypatch, **options)
    redis = FixtureRedis()
    with pytest.raises(RuntimeError):
        await fetch_internetdb(IP, settings=get_settings(), redis=redis)
    assert not any(key == f"straz:internetdb:{IP}" for key, _ in redis.writes)


async def test_complete_provider_record_preserves_high_vulnerability(monkeypatch):
    fixture_http(monkeypatch, body=HOST)
    redis = FixtureRedis()
    findings = await fetch_internetdb(IP, settings=get_settings(), redis=redis)
    assert any(item.severity == "high" and "CVE-2026-0001" in item.title for item in findings)
    assert json.loads(redis.writes[-1][1]) == HOST


async def test_provider_no_information_404_is_a_valid_empty_lookup(monkeypatch):
    fixture_http(monkeypatch, status=404, body={"detail": "No information available"})
    assert await fetch_internetdb(IP, settings=get_settings()) == []


@pytest.mark.parametrize("cached", [b"{}", b"[]", b"not-json", json.dumps({**HOST, "ip": "1.1.1.1"})])
async def test_invalid_cached_record_is_refetched_before_observation(monkeypatch, cached):
    requests = fixture_http(monkeypatch, body=HOST)
    findings = await fetch_internetdb(IP, settings=get_settings(), redis=FixtureRedis(cached))
    assert len(requests) == 1
    assert any(item.severity == "high" for item in findings)


@pytest.mark.parametrize("case", ["timeout", "429", "503", "malformed", "missing-fields", "dns", "404-html", "valid-empty", "valid-high", "valid-404"])
async def test_real_worker_and_ci_preserve_findings_unless_lookup_is_complete(
    auth_client, db_session, test_user, monkeypatch, case,
):
    """API -> actual worker -> actual InternetDB parser -> DB -> actual CI gate."""
    from app import worker

    org_id = await db_session.scalar(select(OrganizationMember.org_id).where(OrganizationMember.user_id == test_user.id))
    app = App(id=uuid.uuid4(), organization_id=org_id, name="InternetDB fixture", base_url="https://app.example.com")
    db_session.add(app)
    await db_session.flush()
    target = Target(id=uuid.uuid4(), app_id=app.id, host="app.example.com", status=TargetStatus.verified, verify_token="synthetic-proof")
    old = Finding(id=uuid.uuid4(), app_id=app.id, target_id=target.id, source=FindingSource.internetdb,
        severity=FindingSeverity.high, title="Previously observed CVE", fingerprint="old-internetdb-cve", status=FindingStatus.open)
    db_session.add_all([target, old])
    await db_session.commit()
    app_id, old_id = app.id, old.id
    complete = case in {"valid-empty", "valid-high", "valid-404"}
    resolve_calls = 0

    async def resolve(*args):
        nonlocal resolve_calls
        resolve_calls += 1
        if case == "dns" and resolve_calls > 1:
            raise OSError("Synthetic second DNS lookup failure")
        return [IP] if complete else [IP, "1.1.1.1"]

    requests = []

    async def wire(self, request):
        requests.append(request)
        # A successful first address must not survive a partial scan rollback.
        if request.url.path.endswith(IP) and not complete:
            return httpx.Response(200, json=HOST, request=request)
        if case == "timeout":
            raise httpx.ReadTimeout("Synthetic second-address timeout", request=request)
        if case in {"429", "503"}:
            return httpx.Response(int(case), json={"detail": "Unavailable"}, request=request)
        if case == "malformed":
            return httpx.Response(200, content=b"not-json", request=request)
        if case == "missing-fields":
            return httpx.Response(200, json={"ip": "1.1.1.1"}, request=request)
        if case == "404-html":
            return httpx.Response(404, content=b"<h1>Proxy route not found</h1>", request=request)
        if case == "valid-404":
            return httpx.Response(404, json={"detail": "No information available"}, request=request)
        return httpx.Response(200, json={**HOST, "ports": [], "vulns": HOST["vulns"] if case == "valid-high" else []}, request=request)

    async def no_cache(*args):
        pass

    class ExecutingQueue:
        async def enqueue_job(self, name, run_id):
            assert name == "execute_scan_run"
            await worker.execute_scan_run({"redis": FixtureRedis()}, run_id)
            return object()

    async def queue(*args):
        return ExecutingQueue()

    monkeypatch.setattr(worker, "SessionLocal", async_sessionmaker(db_session.bind, expire_on_commit=False))
    monkeypatch.setattr(worker, "resolve_public_addresses", resolve)
    monkeypatch.setattr(worker, "_invalidate_overview_cache", no_cache)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", wire)
    monkeypatch.setattr("app.routers.ci.get_arq_redis", queue)

    response = await auth_client.post("/api/ci/scan", json={
        "app_id": str(app_id), "profile": "internetdb", "wait": True,
        "timeout_seconds": 2, "fail_on": "high",
    })
    assert response.status_code == (200 if case in {"valid-empty", "valid-404"} else 424), response.text
    assert response.json()["passed"] is (case in {"valid-empty", "valid-404"})
    run = await db_session.get(ScanRun, uuid.UUID(response.json()["run_id"]))
    assert run.status == (RunStatus.done if complete else RunStatus.failed)
    assert run.observations_complete is complete
    previous = await db_session.get(Finding, old_id)
    await db_session.refresh(previous)
    assert previous.status == (FindingStatus.fixed if complete else FindingStatus.open)
    assert (previous.closed_at is not None) is complete
    if not complete:
        assert response.json()["status"] == "failed"
        assert run.error == "Scanner execution failed"
        assert await db_session.scalar(select(func.count()).select_from(ScanRunFinding).where(ScanRunFinding.scan_run_id == run.id)) == 0
        assert await db_session.scalar(select(func.count()).select_from(Finding).where(Finding.app_id == app_id)) == 1
        assert len(requests) == (0 if case == "dns" else 2)
    elif case == "valid-high":
        assert response.json()["summary"]["high"] == 1
