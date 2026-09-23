from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import dns.resolver
import httpx

from app.config import Settings


def extract_hostname(host_or_url: str) -> str:
    value = host_or_url.strip()
    if "://" in value:
        parsed = urlparse(value)
        return (parsed.hostname or value).lower()
    return value.split("/")[0].split(":")[0].lower()


def is_ip_in_trusted_nets(host: str, nets: list[str]) -> bool:
    hostname = extract_hostname(host)
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved = socket.gethostbyname(hostname)
            addr = ipaddress.ip_address(resolved)
        except OSError:
            return False
    for net in nets:
        try:
            if addr in ipaddress.ip_network(net, strict=False):
                return True
        except ValueError:
            continue
    return False


async def verify_dns_txt(hostname: str, token: str) -> bool:
    expected = f"straz-verify={token}"
    try:
        answers = dns.resolver.resolve(hostname, "TXT")
    except Exception:
        return False
    for rdata in answers:
        for txt in rdata.strings:
            text = txt.decode() if isinstance(txt, bytes) else str(txt)
            if text.strip() == expected:
                return True
    return False


async def verify_well_known(base_url: str, token: str) -> bool:
    url = base_url.rstrip("/") + "/.well-known/straz.txt"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return False
            return resp.text.strip() == token
    except httpx.HTTPError:
        return False


async def verify_target(
    *,
    host: str,
    base_url: str,
    token: str,
    settings: Settings,
) -> str | None:
    hostname = extract_hostname(host)
    if await verify_dns_txt(hostname, token):
        return "dns_txt"
    if await verify_well_known(base_url, token):
        return "well_known"
    if await verify_well_known(f"https://{hostname}", token):
        return "well_known"
    if await verify_well_known(f"http://{hostname}", token):
        return "well_known"
    return None
