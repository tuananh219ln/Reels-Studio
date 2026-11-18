"""What the worker last saw of the Page's own comments under a reel (comments_inbox.py): "link" when one holds a
Shopee link, "no_link" when the Page commented without one, "none" when it has not commented; NULL until read. Lets
"Affiliate" tell which posts still lack a link, a link pasted by hand on Facebook included.

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
    op.add_column("publications", sa.Column("own_comment", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("publications", "own_comment")
