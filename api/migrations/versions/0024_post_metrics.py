"""a post's views, shares, comments and reactions on Facebook

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable columns and a new table: the previous api version keeps working during a deploy.
    op.add_column("publications", sa.Column("metrics_tried_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publications", sa.Column("metrics_error", sa.Text(), nullable=True))
    op.add_column("publications", sa.Column("metrics_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "post_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "publication_id",
            sa.Integer(),
            sa.ForeignKey("publications.id", ondelete="CASCADE", name="fk_post_metrics_publication_id_publications"),
            nullable=False,
        ),
        sa.Column("window", sa.String(8), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("reactions", sa.Integer(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_post_metrics"),
    )
    op.create_index("uq_post_metrics_publication_id_window", "post_metrics", ["publication_id", "window"], unique=True)


def downgrade() -> None:
    op.drop_table("post_metrics")
    op.drop_column("publications", "metrics_requested_at")
    op.drop_column("publications", "metrics_error")
    op.drop_column("publications", "metrics_tried_at")
