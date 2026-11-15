"""An article's post that fails for a passing reason is tried again by itself, 1, 5 then 15 minutes later
(decisions 2026-11-15, "article posting retries").

- `publications.auto_retries`: how many of those tries were planned since a member last pressed "Đăng" or "Thử lại".
- `publications.retry_at`: when the next one is queued; null when none is planned.

Revision ID: 0093
Revises: 0092
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("auto_retries", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("publications", sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_publications_retry_at", "publications", ["retry_at"], postgresql_where=sa.text("retry_at IS NOT NULL")
    )


def downgrade() -> None:
    op.drop_index("ix_publications_retry_at", table_name="publications")
    op.drop_column("publications", "retry_at")
    op.drop_column("publications", "auto_retries")
