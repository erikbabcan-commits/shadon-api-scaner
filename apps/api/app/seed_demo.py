"""Run once from the cloud release job: python -m app.seed_demo --confirm-demo."""
import argparse
import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.security import hash_password, verify_password
from app.services.demo import seed_demo


async def main() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == settings.straz_admin_email.lower()))
        if user is None:
            user = User(email=settings.straz_admin_email.lower(), password_hash=hash_password(settings.straz_admin_password))
            db.add(user)
            await db.flush()
        elif not verify_password(user.password_hash, settings.straz_admin_password):
            raise RuntimeError("Configured admin credential does not match; no password was reset")
        counts = await seed_demo(db, user)
        await db.commit()
        print({"synthetic_demo_seeded": True, **counts})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-demo", action="store_true", required=True)
    parser.parse_args()
    asyncio.run(main())
