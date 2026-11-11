"""A topic group's folder in the "Kho tư liệu" ("Tư liệu" on /knowledge, 2026-11-11)

Revision ID: 0076
Revises: 0075
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null: no folder linked. A folder belongs to at most one group (several nulls are allowed).
    op.add_column("knowledge_topics", sa.Column("media_folder", sa.String(200), nullable=True))
    op.create_unique_constraint("uq_knowledge_topics_media_folder", "knowledge_topics", ["media_folder"])


def downgrade() -> None:
    op.drop_constraint("uq_knowledge_topics_media_folder", "knowledge_topics", type_="unique")
    op.drop_column("knowledge_topics", "media_folder")
