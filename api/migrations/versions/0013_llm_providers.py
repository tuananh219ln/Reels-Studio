"""LLM providers set up on /settings/ai, team settings, and the provider a script job used

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("model", sa.String(200), nullable=False, server_default=""),
        sa.Column("key_encrypted", sa.Text(), nullable=True),
        sa.Column("key_tail", sa.String(8), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Only new nullable columns: the previous api version keeps working during a deploy.
    op.add_column("jobs", sa.Column("llm_provider", sa.String(32), nullable=True))
    op.add_column("jobs", sa.Column("llm_model", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "llm_model")
    op.drop_column("jobs", "llm_provider")
    op.drop_table("app_settings")
    op.drop_table("llm_providers")
