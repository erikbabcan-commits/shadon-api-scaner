from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.models import User
from app.routers import apps, auth, findings, runs
from app.security import hash_password


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await bootstrap_admin()
    yield


app = FastAPI(title="Stráž API", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router, prefix="/api")
app.include_router(apps.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(findings.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
