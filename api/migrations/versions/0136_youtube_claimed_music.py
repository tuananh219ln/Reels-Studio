"""Music claimed on YouTube (docs/decisions/2026-11-26-youtube-claimed-music.md).

Adds the "Đã bị claim trên YouTube" flag to the music library and records the first claim found: on 2026-11-26
YouTube's Content ID blocked video 409 worldwide for its background music, the library's "Gentle – Peaceful Gentle
Music" (track 3). Both seeds are guarded by what they must find (the track's name, a YouTube post of video 409), so a
development or test database whose ids mean something else is left alone.

Revision ID: 0136
Revises: 0135
Create Date: 2026-11-26
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None

CLAIM = "Video 409 – HAAWK Publishing, Audiam (Publishing) – 26/11/2026"
VIDEO_CLAIM = (
    "Content ID: 267_the_inspiring_piano_56574246, HAAWK Publishing, Audiam (Publishing), giai điệu/lời. "
    "Bị chặn trên toàn thế giới 26/11/2026; đã xử lý trong YouTube Studio 26/11 (cách xử lý cần xác nhận)."
)


def upgrade() -> None:
    op.add_column(
        "music_tracks", sa.Column("claimed_on_youtube", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("music_tracks", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    op.add_column("music_tracks", sa.Column("claimed_note", sa.Text(), nullable=False, server_default=""))
    op.execute(
        sa.text(
            "UPDATE music_tracks SET claimed_on_youtube = true, claimed_at = '2026-11-26T21:00:00+07:00', "
            "claimed_note = :note WHERE id = 3 AND name LIKE 'Gentle%'"
        ).bindparams(note=CLAIM)
    )
    op.execute(
        sa.text(
            "INSERT INTO video_events (video_id, type, channel, payload) "
            "SELECT 409, 'youtube_claim', 'system', CAST(:payload AS jsonb) "
            "WHERE EXISTS (SELECT 1 FROM publications WHERE video_id = 409 AND platform = 'youtube')"
        ).bindparams(payload=json.dumps({"note": VIDEO_CLAIM}, ensure_ascii=False))
    )


def downgrade() -> None:
    op.execute("DELETE FROM video_events WHERE type IN ('youtube_claim', 'youtube_claim_cleared')")
    op.drop_column("music_tracks", "claimed_note")
    op.drop_column("music_tracks", "claimed_at")
    op.drop_column("music_tracks", "claimed_on_youtube")
