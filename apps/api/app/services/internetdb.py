from __future__ import annotations

import ipaddress
import json

import httpx

from app.config import Settings
from app.services.scanners import ToolFinding


class InternetDBUnavailable(RuntimeError):
    """The lookup produced no complete observation; never a clean scan result."""


def _validate_host_record(ip: str, data: object) -> dict:
    # Required fields/types are the provider's Host schema:
    # https://internetdb.shodan.io/openapi.json
    if not isinstance(data, dict):
        raise InternetDBUnavailable("Incomplete InternetDB response")
    try:
        if not isinstance(data.get("ip"), str) or ipaddress.ip_address(data["ip"]) != ipaddress.ip_address(ip):
            raise ValueError
    except ValueError:
        raise InternetDBUnavailable("InternetDB response has an invalid IP") from None
    for key in ("ports", "cpes", "hostnames", "tags", "vulns"):
        values = data.get(key)
        if not isinstance(values, list):
            raise InternetDBUnavailable("Incomplete InternetDB response")
        if key == "ports":
            valid = all(type(value) is int and 1 <= value <= 65535 for value in values)
        else:
            valid = all(isinstance(value, str) for value in values)
        if not valid:
            raise InternetDBUnavailable("Malformed InternetDB response")
    return data


def findings_from_internetdb(ip: str, data: dict) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    ports = data.get("ports") or []
    for port in ports:
        findings.append(
            ToolFinding(
                title=f"InternetDB open port {port} on {ip}",
                detail=json.dumps({"ip": ip, "port": port}, ensure_ascii=False),
                severity="info",
                fingerprint_key=f"internetdb|{ip}|port|{port}",
            )
        )
    for vuln in data.get("vulns") or []:
        findings.append(
            ToolFinding(
                title=f"InternetDB vuln {vuln} on {ip}",
                detail=json.dumps({"ip": ip, "vuln": vuln}, ensure_ascii=False),
                severity="high",
                fingerprint_key=f"internetdb|{ip}|vuln|{vuln}",
            )
        )
    for cpe in data.get("cpes") or []:
        findings.append(
            ToolFinding(
                title=f"InternetDB CPE on {ip}",
                detail=str(cpe)[:2000],
                severity="info",
                fingerprint_key=f"internetdb|{ip}|cpe|{cpe}",
            )
        )
    hostnames = data.get("hostnames") or []
    if hostnames:
        joined = ",".join(sorted(map(str, hostnames)))
        findings.append(
            ToolFinding(
                title=f"InternetDB hostnames for {ip}",
                detail=joined[:2000],
                severity="info",
                fingerprint_key=f"internetdb|{ip}|hostnames|{joined}",
            )
        )
    return findings


async def fetch_internetdb(
    ip: str,
    *,
    settings: Settings,
    redis=None,
) -> list[ToolFinding]:
    cache_key = f"straz:internetdb:{ip}"
    if redis is not None:
        cached = await redis.get(cache_key)
        if cached:
            try:
                data = _validate_host_record(ip, json.loads(cached))
                return findings_from_internetdb(ip, data)
            except (ValueError, UnicodeError, InternetDBUnavailable):
                # Old/corrupt cache entries are not observations. Refetch and
                # validate before changing findings or recording scan success.
                pass
        # simple 1 req/s gate per IP
        rate_key = f"straz:internetdb:rate:{ip}"
        ok = await redis.set(rate_key, "1", nx=True, ex=1)
        if not ok:
            # wait out by returning empty — caller can retry; prefer stale miss
            pass

    base = settings.internetdb_base_url.rstrip("/")
    url = f"{base}/{ip}"
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            resp = await client.get(url)
    except httpx.HTTPError:
        raise InternetDBUnavailable("InternetDB lookup unavailable") from None

    if resp.status_code not in (200, 404):
        raise InternetDBUnavailable("InternetDB lookup unavailable")

    try:
        data = resp.json()
    except (ValueError, UnicodeError):
        raise InternetDBUnavailable("Malformed InternetDB response") from None

    if resp.status_code == 404:
        # Preserve the provider's explicit no-data result, not a proxy/router
        # 404 or arbitrary error document masquerading as an empty scan.
        if data == {"detail": "No information available"}:
            return []
        raise InternetDBUnavailable("Unexpected InternetDB not-found response")

    data = _validate_host_record(ip, data)

    if redis is not None:
        await redis.set(cache_key, json.dumps(data), ex=settings.internetdb_cache_ttl)

    return findings_from_internetdb(ip, data)
