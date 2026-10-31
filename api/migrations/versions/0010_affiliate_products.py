"""affiliate products: the team's Shopee product list and the ones attached to posted reels

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliate_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_topic_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("shop_name", sa.String(length=200), nullable=False),
        sa.Column("shop_type", sa.String(length=16), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("sold", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("commission_rate", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_topic_id"],
            ["knowledge_topics.id"],
            name="fk_affiliate_products_knowledge_topic_id_knowledge_topics",
        ),
        sa.ForeignKeyConstraint(["checked_by_id"], ["users.id"], name="fk_affiliate_products_checked_by_id_users"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_affiliate_products_created_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_affiliate_products"),
    )
    op.create_table(
        "video_affiliate_products",
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name="fk_video_affiliate_products_video_id_videos", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["affiliate_products.id"],
            name="fk_video_affiliate_products_product_id_affiliate_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("video_id", "product_id", name="pk_video_affiliate_products"),
    )


def downgrade() -> None:
    op.drop_table("video_affiliate_products")
    op.drop_table("affiliate_products")
