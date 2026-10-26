import asyncio
import os
import uuid
import socket
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test environment
os.environ["STRAZ_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["STRAZ_SESSION_SECRET"] = "test-session-secret-at-least-32-chars-long"
os.environ["STRAZ_ADMIN_PASSWORD"] = "test-admin-secret-password-123"
os.environ["STRIPE_WEBHOOK_SECRET"] = "local-signing-secret-for-unit-tests"

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import create_session_token, hash_password

from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture(autouse=True)
def isolated_io(monkeypatch):
    """The application test suite never scans or contacts an external service."""
    import httpx
    from app import rate_limit
    from app import security
    from argon2 import PasswordHasher
    from app.routers import runs, ci
    rate_limit._in_memory_limiter._hits.clear()
    # Small synthetic test hashes only; production PasswordHasher is unchanged.
    monkeypatch.setattr(security, "ph", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1))

    async def deny_http(self, request):
        raise httpx.ConnectError("External HTTP disabled in tests", request=request)

    class LocalQueue:
        async def enqueue_job(self, *args, **kwargs):
            return object()

    async def local_queue(settings):
        return LocalQueue()

    original_connect = socket.socket.connect
    def local_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise OSError("External sockets disabled in tests")
        return original_connect(sock, address)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_http)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(runs, "get_arq_redis", local_queue)
    monkeypatch.setattr(ci, "get_arq_redis", local_queue)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="tester@example.com",
        password_hash=hash_password("SuperSecret123!"),
        token_version=1,
    )
    db_session.add(user)
    await db_session.flush()

    from app.models import Organization, OrganizationMember, OrgRole
    org = Organization(
        id=uuid.uuid4(),
        name="Test Org",
        slug="test-org",
    )
    db_session.add(org)
    await db_session.flush()

    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.id,
        role=OrgRole.owner,
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def auth_client(
    client: AsyncClient, test_user: User
) -> AsyncGenerator[AsyncClient, None]:
    settings = get_settings()
    token = create_session_token(settings, str(test_user.id), test_user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)
    yield client


@pytest.fixture
def allow_cli_profiles(monkeypatch):
    """Logic tests that exercise gating/quota with CLI profiles (scanners are mocked)."""
    import app.routers.ci as ci_router
    import app.routers.runs as runs_router
    import app.worker as worker_mod

    for mod in (ci_router, runs_router, worker_mod):
        monkeypatch.setattr(mod, "CLI_SCANNER_PROFILES", frozenset())
