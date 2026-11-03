"""a post's watch time, reach, replays, follows and retention curve, and where its scenes fall

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

NUMBERS = ("plays", "replays", "reach", "avg_watch_ms", "view_time_ms", "followers")


def upgrade() -> None:
    for name in NUMBERS:
        op.add_column("post_metrics", sa.Column(name, sa.BigInteger(), nullable=True))
    op.add_column("post_metrics", sa.Column("retention", postgresql.JSONB(), nullable=True))
    op.add_column("publications", sa.Column("scene_marks", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("publications", "scene_marks")
    op.drop_column("post_metrics", "retention")
    for name in NUMBERS:
        op.drop_column("post_metrics", name)
