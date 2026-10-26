"""Database migration helper to run Alembic programmatically or via CLI."""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings

logger = logging.getLogger("straz.migrations")


def get_alembic_config() -> Config:
    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(base_dir / "alembic"))
    settings = get_settings()
    alembic_cfg.set_main_option("sqlalchemy.url", settings.normalized_database_url)
    return alembic_cfg


def run_upgrade_head() -> None:
    """Run alembic upgrade head synchronously."""
    logger.info("Running alembic upgrade head...")
    alembic_cfg = get_alembic_config()
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic upgrade head completed successfully.")


async def assert_schema_at_head() -> None:
    """Fail closed unless the database is exactly at the Alembic head.

    The API never creates or alters schema. Migrations run as a separate,
    controlled step (``python -m app.migrations upgrade``) before start-up.
    SQLite (unit tests only) is skipped.
    """
    from sqlalchemy import text

    from app.db import engine

    if engine.dialect.name == "sqlite":
        return
    from alembic.script import ScriptDirectory

    expected = set(ScriptDirectory.from_config(get_alembic_config()).get_heads())
    async with engine.connect() as conn:
        try:
            rows = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
        except Exception as exc:  # table missing / DB unreachable
            raise RuntimeError("Database schema is not migrated; run migrations before starting the API") from exc
    if set(rows) != expected:
        raise RuntimeError("Database schema is not at Alembic head; run migrations before starting the API")
    logger.info("Database schema is at Alembic head.")


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
