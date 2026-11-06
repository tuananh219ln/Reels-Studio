"""Articles are posted like videos: a publication belongs to a video or to an article, and so does an affiliate link

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A post is of a video or of an article, never both, never neither.
    op.alter_column("publications", "video_id", nullable=True)
    op.add_column(
        "publications",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_publications_article_id", "publications", ["article_id"])
    # An article's text as sent, so a retry after a lost answer finds that very post on the Page.
    op.add_column("publications", sa.Column("post_text", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_publications_one_target"), "publications", "(video_id IS NULL) <> (article_id IS NULL)"
    )
    # As for a video: one pending post per article and platform.
    op.create_index(
        "uq_publications_pending_article",
        "publications",
        ["article_id", "platform"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "article_affiliate_products",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("affiliate_products.id", ondelete="CASCADE"), nullable=False
        ),
        sa.PrimaryKeyConstraint("article_id", "product_id", name=op.f("pk_article_affiliate_products")),
    )

    # An affiliate link is made for a video's post or an article's, on one Page.
    op.alter_column("affiliate_links", "video_id", nullable=True)
    op.add_column(
        "affiliate_links",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_affiliate_links_one_target"), "affiliate_links", "(video_id IS NULL) <> (article_id IS NULL)"
    )
    # NULLs never collide in a unique constraint, so each target gets its own partial index.
    op.drop_constraint("uq_affiliate_links_target", "affiliate_links", type_="unique")
    op.create_index(
        "uq_affiliate_links_video",
        "affiliate_links",
        ["product_id", "account_id", "video_id", "fanpage_id"],
        unique=True,
        postgresql_where=sa.text("video_id IS NOT NULL"),
    )
    op.create_index(
        "uq_affiliate_links_article",
        "affiliate_links",
        ["product_id", "account_id", "article_id", "fanpage_id"],
        unique=True,
        postgresql_where=sa.text("article_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_affiliate_links_article", table_name="affiliate_links")
    op.drop_index("uq_affiliate_links_video", table_name="affiliate_links")
    op.execute("DELETE FROM affiliate_links WHERE article_id IS NOT NULL")
    op.create_unique_constraint(
        "uq_affiliate_links_target", "affiliate_links", ["product_id", "account_id", "video_id", "fanpage_id"]
    )
    op.drop_constraint(op.f("ck_affiliate_links_one_target"), "affiliate_links", type_="check")
    op.drop_column("affiliate_links", "article_id")
    op.alter_column("affiliate_links", "video_id", nullable=False)
    op.drop_table("article_affiliate_products")
    op.drop_index("uq_publications_pending_article", table_name="publications")
    # Articles' posts have no video to keep them; their numbers and comments go with them.
    op.execute("DELETE FROM publications WHERE article_id IS NOT NULL")
    op.drop_constraint(op.f("ck_publications_one_target"), "publications", type_="check")
    op.drop_column("publications", "post_text")
    op.drop_index("ix_publications_article_id", table_name="publications")
    op.drop_column("publications", "article_id")
    op.alter_column("publications", "video_id", nullable=False)
