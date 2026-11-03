"""affiliate accounts of each member, Page owners, TikTok videos and manual posts, Shopee suggestions, links and orders

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliate_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("app_id", sa.String(64)),
        sa.Column("secret_encrypted", sa.Text()),
        sa.Column("secret_tail", sa.String(8)),
        sa.Column("profile_url", sa.Text()),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("report_read_at", sa.DateTime(timezone=True)),
        sa.Column("report_error", sa.Text()),
    )
    op.create_index("ix_affiliate_accounts_owner_id", "affiliate_accounts", ["owner_id"])

    # The member who connected a Page owns it; the one who last touched it is the best guess for Pages already there.
    op.add_column("fanpages", sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id")))
    op.execute("UPDATE fanpages SET owner_id = updated_by_id")
    op.add_column(
        "fanpages",
        sa.Column("shopee_account_id", sa.Integer(), sa.ForeignKey("affiliate_accounts.id", ondelete="SET NULL")),
    )

    op.add_column("videos", sa.Column("platform", sa.String(16), server_default="facebook", nullable=False))
    op.add_column("videos", sa.Column("variant_of_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="SET NULL")))
    op.add_column("videos", sa.Column("suggest_requested_at", sa.DateTime(timezone=True)))
    op.add_column("videos", sa.Column("suggest_by_id", sa.Integer(), sa.ForeignKey("users.id")))
    op.add_column("videos", sa.Column("suggested_at", sa.DateTime(timezone=True)))
    op.add_column("videos", sa.Column("suggest_error", sa.Text()))

    op.add_column(
        "publications",
        sa.Column("affiliate_account_id", sa.Integer(), sa.ForeignKey("affiliate_accounts.id", ondelete="SET NULL")),
    )
    op.add_column("publications", sa.Column("post_url", sa.Text()))

    op.add_column("affiliate_products", sa.Column("platform", sa.String(16), server_default="shopee", nullable=False))
    op.alter_column("affiliate_products", "url", nullable=True)
    op.add_column("affiliate_products", sa.Column("page_url", sa.Text()))
    op.add_column("affiliate_products", sa.Column("image_url", sa.Text()))
    op.add_column("affiliate_products", sa.Column("shopee_item_id", sa.BigInteger()))
    op.add_column("affiliate_products", sa.Column("commission_end_at", sa.DateTime(timezone=True)))
    op.add_column("affiliate_products", sa.Column("offer_checked_at", sa.DateTime(timezone=True)))
    op.create_index(
        "uq_affiliate_products_shopee_item",
        "affiliate_products",
        ["shopee_item_id"],
        unique=True,
        postgresql_where=sa.text("shopee_item_id IS NOT NULL"),
    )

    op.create_table(
        "affiliate_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("affiliate_products.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "account_id", sa.Integer(), sa.ForeignKey("affiliate_accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("product_id", "account_id", "video_id", "fanpage_id", name="uq_affiliate_links_target"),
    )

    op.create_table(
        "affiliate_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(200), nullable=False),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("affiliate_products.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
    )
    op.create_index("ix_affiliate_suggestions_video_id", "affiliate_suggestions", ["video_id"])

    op.create_table(
        "affiliate_conversions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id", sa.Integer(), sa.ForeignKey("affiliate_accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="SET NULL")),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="SET NULL")),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_name", sa.String(300), nullable=False),
        sa.Column("commission", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "external_id", name="uq_affiliate_conversions_order"),
    )


def downgrade() -> None:
    op.drop_table("affiliate_conversions")
    op.drop_table("affiliate_suggestions")
    op.drop_table("affiliate_links")
    op.drop_index("uq_affiliate_products_shopee_item", table_name="affiliate_products")
    for column in ("offer_checked_at", "commission_end_at", "shopee_item_id", "image_url", "page_url", "platform"):
        op.drop_column("affiliate_products", column)
    op.execute("DELETE FROM affiliate_products WHERE url IS NULL")
    op.alter_column("affiliate_products", "url", nullable=False)
    op.drop_column("publications", "post_url")
    op.drop_column("publications", "affiliate_account_id")
    op.execute("DELETE FROM publications WHERE platform = 'tiktok'")
    for column in (
        "suggest_error",
        "suggested_at",
        "suggest_by_id",
        "suggest_requested_at",
        "variant_of_id",
        "platform",
    ):
        op.drop_column("videos", column)
    op.drop_column("fanpages", "shopee_account_id")
    op.drop_column("fanpages", "owner_id")
    op.drop_table("affiliate_accounts")
