"""A video can be posted again: one row per post, one pending at a time, who closed it, when Facebook was checked

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_publications_video_id_platform", "publications", type_="unique")
    op.create_index(
        "uq_publications_pending",
        "publications",
        ["video_id", "platform"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.add_column("publications", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publications", sa.Column("closed_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_publications_closed_by_id_users", "publications", "users", ["closed_by_id"], ["id"])
    op.add_column("publications", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("publication_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Fails while a video has more than one post on a platform; the old schema cannot hold that.
    op.drop_column("jobs", "publication_id")
    op.drop_column("publications", "checked_at")
    op.drop_constraint("fk_publications_closed_by_id_users", "publications", type_="foreignkey")
    op.drop_column("publications", "closed_by_id")
    op.drop_column("publications", "closed_at")
    op.drop_index("uq_publications_pending", table_name="publications")
    op.create_unique_constraint("uq_publications_video_id_platform", "publications", ["video_id", "platform"])
