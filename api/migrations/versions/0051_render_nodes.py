"""Render machines: a member's own computer takes the team's render and motion jobs over HTTPS

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "render_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_render_nodes_created_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_render_nodes"),
        sa.UniqueConstraint("token_hash", name="uq_render_nodes_token_hash"),
    )
    op.add_column("jobs", sa.Column("node_stage", sa.String(length=8), nullable=True))
    op.add_column("jobs", sa.Column("node_id", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("node_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_jobs_node_id_render_nodes", "jobs", "render_nodes", ["node_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_node_id_render_nodes", "jobs", type_="foreignkey")
    op.drop_column("jobs", "node_seen_at")
    op.drop_column("jobs", "node_id")
    op.drop_column("jobs", "node_stage")
    op.drop_table("render_nodes")
