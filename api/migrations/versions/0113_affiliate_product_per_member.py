"""A Shopee product may be listed once per member and group, each with that member's own link.

Revision ID: 0113
Revises: 0112
"""

import sqlalchemy as sa
from alembic import op

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The old index allowed one row per Shopee item for the whole team, so a teammate's import skipped the item.
    # Every existing row is unique by item, so it is unique under the wider key too: no data changes.
    op.drop_index("uq_affiliate_products_shopee_item", table_name="affiliate_products")
    op.create_index(
        "uq_affiliate_products_member_item",
        "affiliate_products",
        ["shopee_item_id", "created_by_id", "knowledge_topic_id"],
        unique=True,
        postgresql_where=sa.text("shopee_item_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Only possible while no item is listed twice; otherwise the copies of the later members are removed first.
    op.execute(
        """
        DELETE FROM affiliate_products WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (PARTITION BY shopee_item_id ORDER BY id) AS n
                FROM affiliate_products WHERE shopee_item_id IS NOT NULL
            ) ranked WHERE n > 1
        )
        """
    )
    op.drop_index("uq_affiliate_products_member_item", table_name="affiliate_products")
    op.create_index(
        "uq_affiliate_products_shopee_item",
        "affiliate_products",
        ["shopee_item_id"],
        unique=True,
        postgresql_where=sa.text("shopee_item_id IS NOT NULL"),
    )
