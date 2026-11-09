"""Each member's own template for new videos ("Mẫu cho video mới"), in place of the team's one app setting

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # "app" or an edit_templates id; null: no template (every member starts there, the team's choice is not copied).
    op.add_column("users", sa.Column("edit_template_default", postgresql.JSONB(), nullable=True))
    # The team's one switch is gone: nothing reads it any more.
    op.execute("DELETE FROM app_settings WHERE key = 'edit_template_default'")


def downgrade() -> None:
    op.drop_column("users", "edit_template_default")
