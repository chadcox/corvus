"""performance indexes and timescale schema

Revision ID: 20260601_0004
Revises: 20260601_0003
Create Date: 2026-06-01 00:30:00
"""

from __future__ import annotations

from alembic import op

from app.schema_migrations import ensure_performance_indexes, ensure_timescale_schema

revision = "20260601_0004"
down_revision = "20260601_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    engine = op.get_bind().engine
    ensure_performance_indexes(engine)
    ensure_timescale_schema(engine)


def downgrade() -> None:
    pass
