"""Add ingest job error taxonomy columns.

Revision ID: 20260601_0006
Revises: 20260601_0005
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260601_0006"
down_revision = "20260601_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingest_jobs", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("ingest_jobs", sa.Column("error_stage", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("ingest_jobs", "error_stage")
    op.drop_column("ingest_jobs", "error_code")
