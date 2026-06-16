"""hash, auth, and column-width schema upgrades

Revision ID: 20260601_0003
Revises: 20260601_0002
Create Date: 2026-06-01 00:20:00
"""

from __future__ import annotations

from alembic import op

from app.schema_migrations import (
    ensure_auth_schema,
    ensure_hash_schema,
    ensure_large_size_columns,
)

revision = "20260601_0003"
down_revision = "20260601_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    engine = op.get_bind().engine
    ensure_hash_schema(engine)
    ensure_large_size_columns(engine)
    ensure_auth_schema(engine)


def downgrade() -> None:
    pass
