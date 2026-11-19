"""How many times in a row the worker has retried a post's failed "Bộ bình luận" comment by itself (after 1, 3 and 10
minutes; post_comments.AFF_RETRIES), so a passing Facebook error no longer waits for "Bình luận ngay".

Revision ID: 0114
Revises: 0113
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("aff_retries", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("publications", "aff_retries")
