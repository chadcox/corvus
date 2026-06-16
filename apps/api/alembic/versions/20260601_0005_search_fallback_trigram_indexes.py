"""add trigram indexes for fallback search columns

Revision ID: 20260601_0005
Revises: 20260601_0004
Create Date: 2026-06-01 01:25:00
"""

from __future__ import annotations

from alembic import op

revision = "20260601_0005"
down_revision = "20260601_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_timeline_events_summary_trgm "
        "ON timeline_events USING gin (summary gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_filesystem_nodes_full_path_trgm "
        "ON filesystem_nodes USING gin (full_path gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_filesystem_nodes_name_trgm "
        "ON filesystem_nodes USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_display_name_trgm "
        "ON entities USING gin (display_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_entity_type_trgm "
        "ON entities USING gin (entity_type gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entities_entity_type_trgm")
    op.execute("DROP INDEX IF EXISTS ix_entities_display_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_filesystem_nodes_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_filesystem_nodes_full_path_trgm")
    op.execute("DROP INDEX IF EXISTS ix_timeline_events_summary_trgm")
