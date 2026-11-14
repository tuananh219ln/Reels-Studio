"""Facebook reels posted outside the app (Meta Business Suite) are imported and matched to videos ("Bài đăng" part 3).

- `publications.match_status`: confirmed (its video known), suggested, unmatched, external ("Video ngoài": followed
  without a video), ignored (hidden, no longer read); `match_score`, `suggested_video_id`; what the platform says of
  the post: `caption`, `duration_sec`, `thumbnail_url`.
- A post may have neither a video nor an article when it was imported (`meta_suite`) or recorded by link as
  "Video ngoài" (`manual_link`).
- `fanpages`: whether its reels posted elsewhere are imported (`sync_external_posts`, on by default), and when that
  last ran, was tried, was asked for, and what went wrong.

Revision ID: 0089
Revises: 0088
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

TARGET = (
    "(video_id IS NULL OR article_id IS NULL) "
    "AND (video_id IS NOT NULL OR article_id IS NOT NULL OR source IN ('meta_suite', 'manual_link'))"
)


def upgrade() -> None:
    op.add_column("publications", sa.Column("match_status", sa.String(16), nullable=False, server_default="confirmed"))
    op.add_column("publications", sa.Column("match_score", sa.Float(), nullable=True))
    op.add_column(
        "publications",
        sa.Column("suggested_video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("publications", sa.Column("caption", sa.Text(), nullable=True))
    op.add_column("publications", sa.Column("duration_sec", sa.Float(), nullable=True))
    op.add_column("publications", sa.Column("thumbnail_url", sa.Text(), nullable=True))
    op.drop_constraint(op.f("ck_publications_one_target"), "publications", type_="check")
    op.create_check_constraint(op.f("ck_publications_one_target"), "publications", TARGET)
    op.create_index(
        "ix_publications_unmatched",
        "publications",
        ["match_status"],
        postgresql_where=sa.text("video_id IS NULL AND article_id IS NULL"),
    )
    op.add_column("fanpages", sa.Column("sync_external_posts", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("fanpages", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fanpages", sa.Column("sync_tried_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fanpages", sa.Column("sync_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fanpages", sa.Column("sync_error", sa.Text(), nullable=True))


def downgrade() -> None:
    for name in ("sync_error", "sync_requested_at", "sync_tried_at", "last_synced_at", "sync_external_posts"):
        op.drop_column("fanpages", name)
    op.drop_index("ix_publications_unmatched", table_name="publications")
    # Posts with neither a video nor an article cannot exist before: they go with their numbers.
    op.execute("DELETE FROM publications WHERE video_id IS NULL AND article_id IS NULL")
    op.drop_constraint(op.f("ck_publications_one_target"), "publications", type_="check")
    op.create_check_constraint(
        op.f("ck_publications_one_target"), "publications", "(video_id IS NULL) <> (article_id IS NULL)"
    )
    for name in ("thumbnail_url", "duration_sec", "caption", "suggested_video_id", "match_score", "match_status"):
        op.drop_column("publications", name)
