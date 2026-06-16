"""metadata, cascade constraints, and sigma schema

Revision ID: 20260601_0002
Revises: 20260601_0001
Create Date: 2026-06-01 00:10:00
"""

from __future__ import annotations

from alembic import op

from app.schema_migrations import (
    ensure_cascade_deletes,
    ensure_evidence_source_metadata_schema,
    ensure_sigma_schema,
)

revision = "20260601_0002"
down_revision = "20260601_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    engine = op.get_bind().engine
    ensure_evidence_source_metadata_schema(engine)
    ensure_cascade_deletes(engine)
    ensure_sigma_schema(engine)


def downgrade() -> None:
    pass
