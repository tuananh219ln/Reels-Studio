"""affiliate_products.lookup_*: a pasted Shopee link or an imported row waits for the worker to read the product

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliate_products", sa.Column("lookup_requested_at", sa.DateTime(timezone=True)))
    op.add_column("affiliate_products", sa.Column("lookup_by_id", sa.Integer(), sa.ForeignKey("users.id")))
    op.add_column("affiliate_products", sa.Column("lookup_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("affiliate_products", "lookup_error")
    op.drop_column("affiliate_products", "lookup_by_id")
    op.drop_column("affiliate_products", "lookup_requested_at")
