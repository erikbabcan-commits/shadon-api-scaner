from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select, text

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.models import User
from app.routers import apps, auth, findings, runs
from app.security import hash_password

# Additive columns for existing Postgres volumes (create_all does not ALTER).
_SCHEMA_PATCHES = [
    "ALTER TABLE apps ADD COLUMN IF NOT EXISTS internetdb_enabled BOOLEAN DEFAULT true",
    "ALTER TABLE apps ADD COLUMN IF NOT EXISTS subdomain_enabled BOOLEAN DEFAULT true",
    "ALTER TABLE apps ADD COLUMN IF NOT EXISTS ports_enabled BOOLEAN DEFAULT true",
    "ALTER TABLE apps ADD COLUMN IF NOT EXISTS trivy_enabled BOOLEAN DEFAULT true",
    "ALTER TABLE apps ADD COLUMN IF NOT EXISTS gitleaks_enabled BOOLEAN DEFAULT true",
    "ALTER TABLE apps ADD COLUMN IF NOT EXISTS git_url VARCHAR(500)",
    "ALTER TABLE apps ADD COLUMN IF NOT EXISTS image_ref VARCHAR(500)",
    "ALTER TABLE scan_runs ALTER COLUMN profile TYPE VARCHAR(32)",
    "ALTER TABLE findings ALTER COLUMN source TYPE VARCHAR(32)",
]


async def bootstrap_admin() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == settings.straz_admin_email.lower()))
        if existing:
            return
        db.add(
            User(
                email=settings.straz_admin_email.lower(),
                password_hash=hash_password(settings.straz_admin_password),
            )
        )
        await db.commit()


async def ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _SCHEMA_PATCHES:
            await conn.execute(text(stmt))


@asynccontextmanager
async def lifespan(_: FastAPI):
    await ensure_schema()
    await bootstrap_admin()
    yield


app = FastAPI(title="Stráž API", version="0.2.0", lifespan=lifespan)

app.include_router(auth.router, prefix="/api")
app.include_router(apps.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(findings.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
