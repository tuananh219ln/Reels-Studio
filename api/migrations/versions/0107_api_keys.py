"""Backup narration keys of the team (api_keys), tried after the main key once it fails. The main key stays where it
is (app_settings "source_keys"), so nothing is moved.

Revision ID: 0107
Revises: 0106
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(20), nullable=False),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("key_encrypted", sa.Text(), nullable=False),
        sa.Column("tail", sa.String(8), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_keys_service_position", "api_keys", ["service", "position"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_service_position", table_name="api_keys")
    op.drop_table("api_keys")
