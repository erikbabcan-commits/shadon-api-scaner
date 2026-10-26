"""Public-only HTTP transport: validate all DNS answers, pin IP, preserve Host/SNI.

No environment proxies and no automatic redirects. Each new request is checked
again at the transport boundary; validating a URL before ordinary DNS is unsafe.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket

import httpx


def validate_public_url(value: str, *, https_only: bool = False) -> httpx.URL:
    if any(ord(c) < 33 for c in value) or "\\" in value:
        raise ValueError("Invalid URL")
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        raise ValueError("Invalid URL") from None
    if url.scheme not in (("https",) if https_only else ("http", "https")):
        raise ValueError("Unsupported URL scheme")
    if not url.host or url.userinfo or url.fragment:
        raise ValueError("URL must have a host and no credentials or fragment")
    host = url.host.rstrip(".").lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Non-public destination")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not is_public_address(str(address)):
        raise ValueError("Non-public destination")
    return url


def is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


async def resolve_public_addresses(host: str, port: int) -> list[str]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        async with asyncio.timeout(2):
            answers = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
    else:
        addresses = [str(literal)]
    if not addresses or any(not is_public_address(address) for address in addresses):
        raise ValueError("Non-public DNS destination")
    return addresses


class PublicHTTPTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = validate_public_url(str(request.url))
        addresses = await resolve_public_addresses(url.host, url.port or (443 if url.scheme == "https" else 80))
        pinned = httpx.Request(
            request.method,
            url.copy_with(host=addresses[0]),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": url.host},
        )
        # Host still identifies the original authority, not the pinned IP.
        pinned.headers["Host"] = url.netloc.decode("ascii")
        return await super().handle_async_request(pinned)


def public_http_client(timeout: float = 5.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=PublicHTTPTransport(retries=0),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )
