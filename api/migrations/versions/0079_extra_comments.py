"""A video's "Bình luận thêm", and the ids of those written under each of its posts

Revision ID: 0079
Revises: 0078
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("extra_comments", postgresql.JSONB(), server_default="[]", nullable=False))
    op.add_column(
        "publications", sa.Column("extra_comment_ids", postgresql.JSONB(), server_default="[]", nullable=False)
    )
    op.add_column(
        "publications", sa.Column("extra_comment_texts", postgresql.JSONB(), server_default="[]", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("publications", "extra_comment_texts")
    op.drop_column("publications", "extra_comment_ids")
    op.drop_column("videos", "extra_comments")
