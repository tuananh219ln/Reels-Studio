"""The schedule of a post's readings and its marks ("Bài đăng" part 2).

- `publications.next_snapshot_at`: when the worker reads the post next; None once it stops (90 days) or before its
  first reading.
- `publications.views_1h|24h|48h|7d|30d`: the views at each mark, set once; `marks_estimated` names the marks taken
  between two readings.
- `publications.gone_since`: the first reading a YouTube post was missing; two such readings an hour apart mark it
  removed.
- `users.views_refreshed_at`: the member's last "Cập nhật view" on "Bài đăng" (once per 5 minutes).

Revision ID: 0088
Revises: 0087
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

MARKS = ("1h", "24h", "48h", "7d", "30d")


def upgrade() -> None:
    op.add_column("publications", sa.Column("next_snapshot_at", sa.DateTime(timezone=True), nullable=True))
    for mark in MARKS:
        op.add_column("publications", sa.Column(f"views_{mark}", sa.BigInteger(), nullable=True))
    op.add_column(
        "publications",
        sa.Column("marks_estimated", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("publications", sa.Column("gone_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("views_refreshed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_publications_next_snapshot_at",
        "publications",
        ["next_snapshot_at"],
        postgresql_where=sa.text("next_snapshot_at IS NOT NULL"),
    )
    # The 48-hour mark kept so far is the new column's.
    op.execute(
        """
        UPDATE publications p SET views_48h = m.views
        FROM post_metrics m WHERE m.publication_id = p.id AND m."window" = '48h'
        """
    )
    # Posts still followed (live within 90 days) are read again soon, on the new schedule.
    op.execute(
        """
        UPDATE publications SET next_snapshot_at = now()
        WHERE video_id IS NOT NULL
          AND status IN ('published', 'scheduled')
          AND COALESCE(scheduled_at, published_at, created_at) > now() - interval '90 days'
          AND ((platform = 'facebook' AND remote_id IS NOT NULL)
               OR (platform = 'youtube' AND external_id IS NOT NULL))
        """
    )


def downgrade() -> None:
    op.drop_index("ix_publications_next_snapshot_at", table_name="publications")
    op.drop_column("users", "views_refreshed_at")
    op.drop_column("publications", "gone_since")
    op.drop_column("publications", "marks_estimated")
    for mark in MARKS:
        op.drop_column("publications", f"views_{mark}")
    op.drop_column("publications", "next_snapshot_at")
