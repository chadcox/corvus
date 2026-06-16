"""baseline schema from existing startup mutators

Revision ID: 20260601_0001
Revises: None
Create Date: 2026-06-01 00:00:00
"""

from __future__ import annotations

from alembic import op

from app.database import Base
from app import models  # noqa: F401
# revision identifiers, used by Alembic.
revision = "20260601_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Baseline migration is intentionally non-destructive for existing environments.
    pass
