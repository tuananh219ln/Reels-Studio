"""Each member's last picked Page and topic group, which the forms start on

Revision ID: 0061
Revises: 0060
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_last_choices",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "knowledge_topic_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_last_choices")
