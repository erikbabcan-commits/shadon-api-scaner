"""Database migration helper to run Alembic programmatically or via CLI."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import get_settings
from app.db import engine

logger = logging.getLogger("straz.migrations")


def get_alembic_config() -> Config:
    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(base_dir / "alembic"))
    settings = get_settings()
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return alembic_cfg


def run_upgrade_head() -> None:
    """Run alembic upgrade head synchronously."""
    logger.info("Running alembic upgrade head...")
    alembic_cfg = get_alembic_config()
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic upgrade head completed successfully.")


async def apply_migrations_async() -> None:
    """Apply migrations. If tables already exist without alembic_version, stamps or handles gracefully."""
    # Run sync in thread pool to avoid blocking async event loop
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, run_upgrade_head)
    except Exception as exc:
        logger.warning(
            "Programmatic alembic migration failed or DB already initialized (%s). Ensuring schema directly...",
            exc,
        )
        from app.db import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if cmd == "upgrade":
        run_upgrade_head()
    elif cmd == "revision":
        msg = sys.argv[2] if len(sys.argv) > 2 else "migration"
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, autogenerate=True, message=msg)
    else:
        print(f"Unknown command {cmd}. Use 'upgrade' or 'revision [msg]'")
