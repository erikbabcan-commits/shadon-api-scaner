"""Real outbox→TCP/TLS receipt on a private loopback-only HTTPS fixture.

The fixture simulates a public webhook hostname: only its exact DNS result is
mapped to loopback, its generated CA is trusted explicitly, and the suite's
HTTP deny hook is relaxed only for the exact pinned IP/port/Host/SNI tuple.
Production destination validation is unchanged. No external notification is
sent, TLS verification is never disabled, and temporary keys stay in tmp_path.
"""
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import shutil
import ssl
import subprocess

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models import AlertEvent
from app.services import notifications, safe_http
from app.services.notifications.transport import send_to_channel
from test_notification_outbox import NOW, seed


# Module collection precedes autouse isolated_io. This original implementation
# still performs the actual httpcore socket connection and TLS handshake.
_REAL_HTTP_REQUEST = httpx.AsyncHTTPTransport.handle_async_request
FIXTURE_HOST = "notify.straz-fixture.test"


def certificates(directory: Path):
    executable = shutil.which("openssl")
    assert executable, "OpenSSL is required for the real TLS integration test"

    def openssl(*arguments):
        subprocess.run([executable, *arguments], check=True, capture_output=True, timeout=30)

    ca_key, ca_cert = directory / "ca.key", directory / "ca.crt"
    server_key, server_cert = directory / "server.key", directory / "server.crt"
    csr, extensions = directory / "server.csr", directory / "server.ext"
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(ca_key),
            "-out", str(ca_cert), "-days", "1", "-subj", "/CN=Straz Local Fixture CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(server_key),
            "-out", str(csr), "-subj", f"/CN={FIXTURE_HOST}")
    extensions.write_text(
        f"subjectAltName=DNS:{FIXTURE_HOST}\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
    )
    openssl("x509", "-req", "-in", str(csr), "-CA", str(ca_cert), "-CAkey", str(ca_key),
            "-CAcreateserial", "-out", str(server_cert), "-days", "1", "-sha256",
            "-extfile", str(extensions))
    ca_key.chmod(0o600)
    server_key.chmod(0o600)
    return ca_cert, server_cert, server_key


async def test_outbox_retries_real_verified_https_with_stable_identity_and_exact_hmac(tmp_path, monkeypatch):
    ca_cert, server_cert, server_key = await asyncio.to_thread(certificates, tmp_path)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(server_cert, server_key)
    received_sni = []
    server_context.set_servername_callback(lambda _ssl, name, _context: received_sni.append(name))
    trusted_context = ssl.create_default_context(cafile=str(ca_cert))
    assert trusted_context.verify_mode == ssl.CERT_REQUIRED and trusted_context.check_hostname
    receipts = []
    receiver_errors = []
    receiver_tasks = set()

    async def receiver(reader, writer):
        task = asyncio.current_task()
        receiver_tasks.add(task)
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=3)
            lines = head.decode("ascii").split("\r\n")
            headers = {name.lower(): value.strip() for name, value in
                       (line.split(":", 1) for line in lines[1:] if line)}
            length = int(headers["content-length"])
            assert 0 < length <= 65536
            body = await asyncio.wait_for(reader.readexactly(length), timeout=3)
            tls = writer.get_extra_info("ssl_object")
            assert tls is not None
            receipts.append((lines[0], headers, body, tls.version()))
            status = "503 Service Unavailable" if len(receipts) == 1 else "200 OK"
            writer.write(f"HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode("ascii"))
            await writer.drain()
        except Exception as exc:
            receiver_errors.append(type(exc).__name__)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, ssl.SSLError):
                # HTTPX may reset its already-consumed Connection: close socket.
                # The complete request/response was captured above; do not turn
                # the peer's shutdown timing into a receipt failure.
                pass
            finally:
                receiver_tasks.discard(task)

    server = await asyncio.start_server(receiver, "127.0.0.1", 0, ssl=server_context,
                                        ssl_handshake_timeout=3)
    port = server.sockets[0].getsockname()[1]
    destination = f"https://{FIXTURE_HOST}:{port}/outbox"
    real_public_transport = safe_http.PublicHTTPTransport
    denied_request = httpx.AsyncHTTPTransport.handle_async_request
    clock = [NOW]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.sqlite3'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def fixture_dns(host, requested_port):
        if host != FIXTURE_HOST or requested_port != port:
            raise ValueError("DNS is permitted only for the exact local TLS fixture")
        return ["127.0.0.1"]

    async def guarded_real_wire(self, request):
        if not (
            request.url.scheme == "https" and request.url.host == "127.0.0.1"
            and request.url.port == port and request.url.path == "/outbox"
            and request.headers.get("Host") == f"{FIXTURE_HOST}:{port}"
            and request.extensions.get("sni_hostname") == FIXTURE_HOST
        ):
            return await denied_request(self, request)
        return await _REAL_HTTP_REQUEST(self, request)

    # Keep the real public_http_client and PublicHTTPTransport implementation;
    # inject an SSLContext that explicitly trusts only this test's CA.
    trust = [ssl.create_default_context()]

    def fixture_transport(*args, **kwargs):
        assert "verify" not in kwargs
        assert trust[0].verify_mode == ssl.CERT_REQUIRED and trust[0].check_hostname
        return real_public_transport(*args, verify=trust[0], **kwargs)

    monkeypatch.setattr(safe_http, "resolve_public_addresses", fixture_dns)
    monkeypatch.setattr(safe_http, "PublicHTTPTransport", fixture_transport)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", guarded_real_wire)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    monkeypatch.setattr(notifications, "_utcnow", lambda: clock[0])
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            _, _, channel, event = await seed(db)
            channel.destination_url = destination
            channel.secret_token = "local-tls-outbox-fixture"
            event.title = "Lokálny TLS výpadok"
            event.detail = "Dočasný test prijatia upozornenia"
            await db.commit()

        # A real handshake without this fixture CA must fail before any HTTP
        # receipt. A disabled certificate check would make this assertion fail.
        assert not await send_to_channel(channel, "test.alert", "info", "TLS negative fixture", None, None)
        assert receipts == []
        trust[0] = trusted_context

        # The network-deny barrier remains effective for arbitrary base HTTPX
        # requests, including direct access to this listener without pinned SNI.
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(verify=trusted_context), trust_env=False) as client:
            with pytest.raises(httpx.ConnectError, match="External HTTP disabled"):
                await client.get(f"https://127.0.0.1:{port}/outbox")

        await notifications.process_alert_outbox({})
        async with factory() as db:
            first = await db.get(AlertEvent, event.id)
            assert first.status == "pending" and first.attempt_count == 1
            assert first.next_attempt_at is not None
            clock[0] = notifications._aware(first.next_attempt_at)
        assert len(receipts) == 1
        await notifications.process_alert_outbox({})
        async with factory() as db:
            completed = await db.get(AlertEvent, event.id)
            assert completed.status == "sent" and completed.attempt_count == 2
            assert completed.processed_at is not None
            assert completed.lease_token is None and completed.lease_expires_at is None
        assert len(receipts) == 2
        for request_line, headers, raw_body, version in receipts:
            assert request_line == "POST /outbox HTTP/1.1"
            assert headers["host"] == f"{FIXTURE_HOST}:{port}"
            expected = hmac.new(b"local-tls-outbox-fixture", raw_body, hashlib.sha256).hexdigest()
            assert headers["x-straz-signature"] == "sha256=" + expected
            assert headers["idempotency-key"] == json.loads(raw_body)["event_id"] == str(event.id)
            assert version in {"TLSv1.2", "TLSv1.3"}
        assert received_sni and all(name == FIXTURE_HOST for name in received_sni)
        assert receiver_errors == []
    finally:
        server.close()
        await server.wait_closed()
        if receiver_tasks:
            await asyncio.wait_for(asyncio.gather(*list(receiver_tasks)), timeout=5)
        await engine.dispose()
