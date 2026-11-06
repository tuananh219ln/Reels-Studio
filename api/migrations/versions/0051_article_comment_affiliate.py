"""An article's pinned comment and product ideas, and Shopee suggestions for an article as for a video

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # What the comment under the post opens with, before the products' links, as a video's pinned comment.
    op.add_column("articles", sa.Column("pinned_comment", sa.Text(), server_default="", nullable=False))
    # Product ideas to search Shopee for, written by the AI or a member; and the search, as on `videos`.
    op.add_column("articles", sa.Column("affiliates", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("articles", sa.Column("suggest_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("articles", sa.Column("suggest_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("articles", sa.Column("suggested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("articles", sa.Column("suggest_error", sa.Text(), nullable=True))

    op.alter_column("affiliate_suggestions", "video_id", nullable=True)
    op.add_column(
        "affiliate_suggestions",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_affiliate_suggestions_article_id", "affiliate_suggestions", ["article_id"])
    op.create_check_constraint(
        op.f("ck_affiliate_suggestions_one_target"),
        "affiliate_suggestions",
        "(video_id IS NULL) <> (article_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_affiliate_suggestions_one_target"), "affiliate_suggestions", type_="check")
    op.execute("DELETE FROM affiliate_suggestions WHERE article_id IS NOT NULL")
    op.drop_index("ix_affiliate_suggestions_article_id", table_name="affiliate_suggestions")
    op.drop_column("affiliate_suggestions", "article_id")
    op.alter_column("affiliate_suggestions", "video_id", nullable=False)
    for column in ("suggest_error", "suggested_at", "suggest_by_id", "suggest_requested_at", "affiliates"):
        op.drop_column("articles", column)
    op.drop_column("articles", "pinned_comment")
