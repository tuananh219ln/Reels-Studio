"""The multi-platform "Bài đăng" board (part 1): where a post came from, the platform's id of it, a TikTok or YouTube
post waiting for its link, YouTube channels, and the time series of a post's numbers.

- `publications.source`: app_api (sent by the app) | manual_link (recorded with its link) | meta_suite (later).
- `publications.external_id`: the platform's id of the post (Facebook video id, TikTok video id, YouTube id),
  unique per platform, so a link pasted twice is caught.
- `publications.status` may now be `pending_link`: the MP4 was downloaded for TikTok or YouTube, the link is not in.
- `channels`: YouTube channels (TikTok accounts stay `affiliate_accounts`, Facebook Pages `fanpages`).
- `post_metric_snapshots`: every reading of a post's numbers; the readings kept so far are copied in.

Revision ID: 0087
Revises: 0086
Create Date: 2026-11-14
"""

import re
from urllib.parse import parse_qs, urlsplit

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

TIKTOK_VIDEO = re.compile(r"/video/(\d{6,25})")
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
INSTAGRAM = re.compile(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)")


def _external_id(platform: str, url: str | None) -> str | None:
    """The id in a link recorded before this migration; None when it cannot be read."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if platform == "tiktok":
        match = TIKTOK_VIDEO.search(parts.path)
        return match.group(1) if match else None
    if platform == "youtube":
        if host == "youtu.be":
            candidate = parts.path.strip("/")
        elif parts.path.startswith("/shorts/"):
            candidate = parts.path.removeprefix("/shorts/").strip("/")
        else:
            candidate = (parse_qs(parts.query).get("v") or [""])[0]
        return candidate if YOUTUBE_ID.match(candidate) else None
    if platform == "instagram":
        match = INSTAGRAM.search(parts.path)
        return match.group(1) if match else None
    return None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("handle", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_channels_platform_handle", "channels", ["platform", sa.text("lower(handle)")], unique=True)

    op.add_column("publications", sa.Column("source", sa.String(16), nullable=False, server_default="app_api"))
    op.add_column("publications", sa.Column("external_id", sa.String(64), nullable=True))
    op.add_column(
        "publications",
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("publications", sa.Column("mp4_downloaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publications", sa.Column("published_at_source", sa.String(8), nullable=True))

    bind = op.get_bind()
    # Recorded by hand: YouTube and Instagram always, TikTok when it was not sent through TikTok's API.
    bind.execute(
        sa.text(
            "UPDATE publications SET source = 'manual_link' "
            "WHERE platform IN ('youtube', 'instagram') OR (platform = 'tiktok' AND publish_mode IS NULL)"
        )
    )
    seen: set[tuple[str, str]] = set()
    rows = bind.execute(
        sa.text(
            "SELECT id, platform, remote_id, post_url FROM publications "
            "WHERE video_id IS NOT NULL OR article_id IS NOT NULL ORDER BY id"
        )
    ).all()
    for post_id, platform, remote_id, post_url in rows:
        # A Facebook post's id is its reel's; a TikTok post sent through the API holds a publish_id, not the video's.
        external = remote_id if platform == "facebook" else _external_id(platform, post_url)
        if not external or (platform, external) in seen:
            continue
        seen.add((platform, external))
        bind.execute(
            sa.text("UPDATE publications SET external_id = :external WHERE id = :id"),
            {"external": external[:64], "id": post_id},
        )
    op.create_index(
        "uq_publications_platform_external_id",
        "publications",
        ["platform", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_index(
        "uq_publications_pending_link",
        "publications",
        ["video_id", "platform"],
        unique=True,
        postgresql_where=sa.text("status = 'pending_link'"),
    )

    op.create_table(
        "post_metric_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publication_id", sa.Integer(), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hours_since_publish", sa.Numeric(8, 2), nullable=True),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("raw", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_post_metric_snapshots_publication_captured", "post_metric_snapshots", ["publication_id", "captured_at"]
    )
    # The readings kept so far (`latest` and the 48-hour mark), once each when both are the same reading.
    bind.execute(
        sa.text(
            """
            INSERT INTO post_metric_snapshots
                (publication_id, captured_at, hours_since_publish, views, likes, comments, shares, raw)
            SELECT DISTINCT ON (m.publication_id, m.measured_at)
                m.publication_id,
                m.measured_at,
                CASE WHEN COALESCE(p.scheduled_at, p.published_at) IS NULL THEN NULL
                     ELSE LEAST(999999.99, GREATEST(0, ROUND(
                         (EXTRACT(EPOCH FROM m.measured_at - COALESCE(p.scheduled_at, p.published_at)) / 3600)::numeric,
                         2))) END,
                m.views, m.reactions, m.comments, m.shares,
                jsonb_build_object('from', 'post_metrics', 'window', m."window")
            FROM post_metrics m JOIN publications p ON p.id = m.publication_id
            ORDER BY m.publication_id, m.measured_at, m."window"
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_post_metric_snapshots_publication_captured", table_name="post_metric_snapshots")
    op.drop_table("post_metric_snapshots")
    # A post still waiting for its link never went out: it goes, as the status does not exist before.
    op.execute("DELETE FROM publications WHERE status = 'pending_link'")
    op.drop_index("uq_publications_pending_link", table_name="publications")
    op.drop_index("uq_publications_platform_external_id", table_name="publications")
    op.drop_column("publications", "published_at_source")
    op.drop_column("publications", "mp4_downloaded_at")
    op.drop_column("publications", "channel_id")
    op.drop_column("publications", "external_id")
    op.drop_column("publications", "source")
    op.drop_index("uq_channels_platform_handle", table_name="channels")
    op.drop_table("channels")
