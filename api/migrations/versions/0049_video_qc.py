"""A rendered MP4 carries its automatic QC: loudness, peaks, black frames, freezes, silence, format and length

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("qc", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "qc")
