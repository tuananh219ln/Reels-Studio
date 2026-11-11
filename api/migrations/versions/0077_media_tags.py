"""Tags on the "Kho tư liệu" items (2026-11-11)

Revision ID: 0077
Revises: 0076
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Lowercase, without accents, joined with "-" (media_tags.clean_tag); [] for none.
    op.add_column(
        "media_items",
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    # "Every tag asked" is `tags @> '[...]'`, which a GIN index answers.
    op.create_index("ix_media_items_tags", "media_items", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_media_items_tags", table_name="media_items")
    op.drop_column("media_items", "tags")
