"""Articles ("Bài viết"): photo or text posts written for a Page, their caption prompt and caption job

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_topic_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("topic", sa.Text(), server_default="", nullable=False),
        sa.Column("caption", sa.Text(), server_default="", nullable=False),
        sa.Column("hashtags", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("image_key", sa.String(200), nullable=True),
        sa.Column("image_kind", sa.String(16), nullable=True),
        sa.Column("image_source", sa.Text(), nullable=True),
        sa.Column(
            "source_comment_id",
            sa.Integer(),
            sa.ForeignKey("page_comments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('kien_thuc', 'meo', 'cau_hoi', 'canh_bao', 'tra_loi_binh_luan', 'checklist')",
            name=op.f("ck_articles_kind"),
        ),
        sa.CheckConstraint(
            "image_kind IS NULL OR image_kind IN ('ai', 'link', 'text_card')", name=op.f("ck_articles_image_kind")
        ),
    )
    op.create_index("ix_articles_created_at", "articles", ["created_at"])
    # "Prompt viết bài" per topic group; empty: prompts/article_default.txt.
    op.add_column("knowledge_topics", sa.Column("article_prompt", sa.Text(), server_default="", nullable=False))
    op.add_column(
        "jobs",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=True),
    )
    # One queued or running job per article, as per video.
    op.create_index(
        "uq_jobs_active_article",
        "jobs",
        ["article_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_active_article", table_name="jobs")
    op.execute("DELETE FROM jobs WHERE article_id IS NOT NULL")
    op.drop_column("jobs", "article_id")
    op.drop_column("knowledge_topics", "article_prompt")
    op.drop_index("ix_articles_created_at", table_name="articles")
    op.drop_table("articles")
