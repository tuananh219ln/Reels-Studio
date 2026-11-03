"""visitors' comments under the app's reels, for "Bình luận"

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("comments_read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publications", sa.Column("comments_error", sa.Text(), nullable=True))
    op.create_table(
        "page_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "publication_id",
            sa.Integer(),
            sa.ForeignKey("publications.id", ondelete="CASCADE", name="fk_page_comments_publication_id_publications"),
            nullable=False,
        ),
        sa.Column("remote_id", sa.String(80), nullable=False),
        sa.Column("author_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("reply_id", sa.String(80), nullable=True),
        sa.Column("reply_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hide_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hide_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "handled_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_page_comments_handled_by_id_users"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_page_comments"),
        sa.UniqueConstraint("remote_id", name="uq_page_comments_remote_id"),
    )
    op.create_index("ix_page_comments_publication_id", "page_comments", ["publication_id"])


def downgrade() -> None:
    op.drop_table("page_comments")
    op.drop_column("publications", "comments_error")
    op.drop_column("publications", "comments_read_at")
