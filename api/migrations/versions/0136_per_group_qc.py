"""A topic group's "QC & duyệt" (`knowledge_topics.qc_config`, qc_config.py) and a video's "Không dùng tiêu đề"
(`videos.no_title`, `videos.kept_title`) (docs/decisions/2026-11-26-per-group-qc.md).

Topic Threads starts with the ranges of its format (no title text, 45–100 s scripts of 5–13 scenes, 60–90 s MP4s);
every other group starts empty, which checks as before. A group missing here (or renamed) starts empty.

Revision ID: 0136
Revises: 0135
Create Date: 2026-11-26
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None

SEED = {
    "Topic Threads": {
        "title_required": False,
        "total_seconds": {"min": 45, "max": 100},
        "scene_count": {"min": 5, "max": 13},
        "channel_seconds": {"min": 60, "max": 90},
    },
}


def upgrade() -> None:
    op.add_column("knowledge_topics", sa.Column("qc_config", JSONB(), nullable=True))
    op.add_column("videos", sa.Column("no_title", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("videos", sa.Column("kept_title", sa.Text(), nullable=True))
    bind = op.get_bind()
    for name, config in SEED.items():
        bind.execute(
            sa.text("UPDATE knowledge_topics SET qc_config = CAST(:config AS jsonb) WHERE name = :name"),
            {"config": json.dumps(config), "name": name},
        )


def downgrade() -> None:
    op.drop_column("videos", "kept_title")
    op.drop_column("videos", "no_title")
    op.drop_column("knowledge_topics", "qc_config")
