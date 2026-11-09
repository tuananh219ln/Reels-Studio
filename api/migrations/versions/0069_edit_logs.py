"""Edit history ("Lịch sử"): one row per create, edit, delete or restore of a thing the team edits

Revision ID: 0069
Revises: 0068
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("label", sa.String(200), nullable=False, server_default=""),
        sa.Column("changes", JSONB(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="web"),
        sa.Column("restored_from_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_edit_logs_entity", "edit_logs", ["entity_type", "entity_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_edit_logs_entity", table_name="edit_logs")
    op.drop_table("edit_logs")
