"""Add cvss_score, cvss_vector, poc_command, and remediation_patch to findings

Revision ID: 009_cvss_and_poc_fields
Revises: 008_postgres_uuid_and_audit_fk
Create Date: 2026-10-28 04:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009_cvss_and_poc_fields"
down_revision: Union[str, None] = "008_postgres_uuid_and_audit_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("cvss_score", sa.Float(), nullable=True))
    op.add_column("findings", sa.Column("cvss_vector", sa.String(length=100), nullable=True))
    op.add_column("findings", sa.Column("poc_command", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("remediation_patch", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "remediation_patch")
    op.drop_column("findings", "poc_command")
    op.drop_column("findings", "cvss_vector")
    op.drop_column("findings", "cvss_score")
