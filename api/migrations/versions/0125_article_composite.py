"""An article's "Ảnh ghép chữ + ảnh": `article_images.opts` keeps what a composite was made from, to open it again.

Revision ID: 0125
Revises: 0124
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("article_images", sa.Column("opts", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("article_images", "opts")
