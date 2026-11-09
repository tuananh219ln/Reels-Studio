"""A stock photo's credit on its scene, and each topic group's order of stock sources (Wikimedia, Unsplash)

Revision ID: 0069
Revises: 0068
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("image_credit", postgresql.JSONB(none_as_null=True), nullable=True))
    op.add_column("knowledge_topics", sa.Column("stock_order", postgresql.JSONB(none_as_null=True), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "stock_order")
    op.drop_column("scenes", "image_credit")
