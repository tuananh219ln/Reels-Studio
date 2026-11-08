""" "Loại nội dung": the content type a member gives a video (Hướng dẫn, Mẹo nhanh...), shown on every list of videos

Revision ID: 0058
Revises: 0057
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("content_type", sa.String(40), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("videos", "content_type")
