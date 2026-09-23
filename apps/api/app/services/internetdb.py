from __future__ import annotations

import ipaddress
import json
import socket

import dns.resolver
import httpx

from app.config import Settings
from app.services.scanners import ToolFinding
from app.services.verify import extract_hostname


def is_public_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def resolve_public_ips(host: str) -> list[str]:
    hostname = extract_hostname(host)
    try:
        addr = ipaddress.ip_address(hostname)
        return [str(addr)] if is_public_ip(addr) else []
    except ValueError:
        pass

    ips: list[str] = []
    for rdtype in ("A", "AAAA"):
        try:
            answers = dns.resolver.resolve(hostname, rdtype)
        except Exception:
            continue
        for rdata in answers:
            try:
                addr = ipaddress.ip_address(str(rdata))
            except ValueError:
                continue
            if is_public_ip(addr):
                ips.append(str(addr))
    if ips:
        return list(dict.fromkeys(ips))

    # fallback getaddrinfo
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if is_public_ip(addr):
                ips.append(str(addr))
    except OSError:
        return []
    return list(dict.fromkeys(ips))


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
            raw = cached.decode() if isinstance(cached, bytes) else cached
            try:
                data = json.loads(raw)
                return findings_from_internetdb(ip, data)
            except json.JSONDecodeError:
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
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        return [
            ToolFinding(
                title=f"InternetDB request failed for {ip}",
                detail=str(exc)[:500],
                severity="low",
                fingerprint_key=f"internetdb|{ip}|error",
            )
        ]

    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        return [
            ToolFinding(
                title=f"InternetDB HTTP {resp.status_code} for {ip}",
                detail=resp.text[:500],
                severity="low",
                fingerprint_key=f"internetdb|{ip}|http|{resp.status_code}",
            )
        ]

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return []

    if redis is not None:
        await redis.set(cache_key, json.dumps(data), ex=settings.internetdb_cache_ttl)

    return findings_from_internetdb(ip, data if isinstance(data, dict) else {})
