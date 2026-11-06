"""A scene can be a "Cảnh động": HyperFrames markup the worker renders into the scene's clip

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("motion", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "motion")
