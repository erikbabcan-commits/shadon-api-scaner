from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import dns.asyncresolver
import httpx

from app.config import Settings
from app.services.safe_http import public_http_client


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
        answers = await dns.asyncresolver.resolve(hostname, "TXT", lifetime=3)
    except Exception:
        return False
    for rdata in answers:
        text = b"".join(rdata.strings).decode("utf-8", errors="replace")
        if text.strip() == expected:
            return True
    return False


async def verify_well_known(base_url: str, token: str) -> bool:
    url = base_url.rstrip("/") + "/.well-known/straz.txt"
    try:
        async with public_http_client(timeout=3) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return False
                body = b""
                async for part in resp.aiter_bytes():
                    body += part
                    if len(body) > 4096:
                        return False
                return body.decode("utf-8", errors="replace").strip() == token
    except (httpx.HTTPError, ValueError, OSError, TimeoutError):
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
    # A proof on the application's unrelated host never verifies a new target.
    parsed = urlparse(base_url)
    if parsed.hostname and parsed.hostname.lower() == hostname:
        authority = parsed.netloc
        if await verify_well_known(f"{parsed.scheme}://{authority}", token):
            return "well_known"
    if await verify_well_known(f"https://{hostname}", token):
        return "well_known"
    if await verify_well_known(f"http://{hostname}", token):
        return "well_known"
    return None
