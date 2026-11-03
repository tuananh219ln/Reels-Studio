"""the affiliate comment the worker writes under a posted reel

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Posts made before this get no comment by themselves: auto_comment is false for them.
    op.add_column(
        "publications", sa.Column("auto_comment", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.add_column("publications", sa.Column("comment_id", sa.String(64), nullable=True))
    op.add_column("publications", sa.Column("comment_text", sa.Text(), nullable=True))
    op.add_column("publications", sa.Column("comment_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publications", sa.Column("commented_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publications", sa.Column("comment_error", sa.Text(), nullable=True))
    op.add_column("publications", sa.Column("comment_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in (
        "comment_requested_at",
        "comment_error",
        "commented_at",
        "comment_sent_at",
        "comment_text",
        "comment_id",
        "auto_comment",
    ):
        op.drop_column("publications", column)
