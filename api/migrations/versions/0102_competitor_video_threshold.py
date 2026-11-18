"""'Phân tích đối thủ': a big channel keeps only its videos of 100K views or more; the numbers are kept apart.

Revision ID: 0102
Revises: 0101
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competitors", sa.Column("video_threshold_mode", sa.String(8), server_default="auto", nullable=False))
    op.add_column("competitor_scans", sa.Column("scanned_count", sa.Integer(), nullable=True))
    op.add_column("competitor_scans", sa.Column("stored_count", sa.Integer(), nullable=True))
    op.add_column("competitor_scans", sa.Column("threshold_applied", sa.BigInteger(), nullable=True))
    op.add_column("competitor_scans", sa.Column("stats_snapshot", JSONB(), nullable=True))


def downgrade() -> None:
    for column in ("stats_snapshot", "threshold_applied", "stored_count", "scanned_count"):
        op.drop_column("competitor_scans", column)
    op.drop_column("competitors", "video_threshold_mode")
