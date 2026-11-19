"""Affiliate comment sets ("Bộ bình luận", docs/decisions/2026-11-19-aff-comment-sets.md): a Page's ready-made
comments of up to 10 products each, written under its reels after the food comments.

- `affiliate_products` gets the short name, group and tags a set's comment and its matching read.
- `aff_comment_sets` / `aff_comment_set_items`: the sets of a Page and their products in order.
- `fanpages.aff_settings`: the Page's settings (aff_sets.DEFAULTS fills what is missing).
- `videos.aff_comments_off` / `videos.aff_set_ids`: a video's own choice (none, or these sets instead of the app's).
- `publications.aff_set_ids` / `aff_comment_ids` / `aff_comment_texts`: the sets a post used, and the comments written
  for them by place, as `extra_comment_ids` / `extra_comment_texts` are kept.

Revision ID: 0111
Revises: 0110
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliate_products", sa.Column("short_name", sa.String(60)))
    op.add_column("affiliate_products", sa.Column("category", sa.String(60)))
    op.add_column("affiliate_products", sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("fanpages", sa.Column("aff_settings", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column(
        "videos", sa.Column("aff_comments_off", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.add_column("videos", sa.Column("aff_set_ids", postgresql.JSONB()))
    op.add_column("publications", sa.Column("aff_set_ids", postgresql.JSONB()))
    op.add_column("publications", sa.Column("aff_comment_ids", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column(
        "publications", sa.Column("aff_comment_texts", postgresql.JSONB(), nullable=False, server_default="[]")
    )
    op.create_table(
        "aff_comment_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("intro_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("outro_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_aff_comment_sets_fanpage_id", "aff_comment_sets", ["fanpage_id"])
    op.create_table(
        "aff_comment_set_items",
        sa.Column("set_id", sa.Integer(), sa.ForeignKey("aff_comment_sets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("affiliate_products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("aff_comment_set_items")
    op.drop_index("ix_aff_comment_sets_fanpage_id", table_name="aff_comment_sets")
    op.drop_table("aff_comment_sets")
    op.drop_column("publications", "aff_comment_texts")
    op.drop_column("publications", "aff_comment_ids")
    op.drop_column("publications", "aff_set_ids")
    op.drop_column("videos", "aff_set_ids")
    op.drop_column("videos", "aff_comments_off")
    op.drop_column("fanpages", "aff_settings")
    op.drop_column("affiliate_products", "tags")
    op.drop_column("affiliate_products", "category")
    op.drop_column("affiliate_products", "short_name")
