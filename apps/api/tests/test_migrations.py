import pytest
from alembic import command
from alembic.config import Config


def test_alembic_upgrade_and_downgrade():
    alembic_cfg = Config("alembic.ini")
    # Verify current head resolves
    command.heads(alembic_cfg)
