"""A topic group's "Giọng đọc theo vai" (`knowledge_topics.voice_format`, voice_format.py) and the name of a scene's
uploaded narration file (`scenes.voice_name`, docs/specs/custom-scene-voice-upload).

The five groups the team builds today start with the formats their build jobs used on 2026-11-26 (owner's table,
checked against the live group settings); their owners edit them on Kho kiến thức. A group missing here (or renamed)
starts empty.

Revision ID: 0127
Revises: 0126
Create Date: 2026-11-25
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0127"
down_revision = "0126"
branch_labels = None
depends_on = None

CHI = "5yEPTrA0uAhZsBEhHjfi"
ADAM = "pNInz6obpgDQGcFmaJgB"
ROGER = "CwhRBWXzGAHq8TQ4Fs17"

SEED = {
    "Ăn Lành Sống Khỏe – Sức khỏe": {"mode": "single", "roles": [{"role": "all", "source": "provider", "voice": CHI}]},
    "Già Mà Khỏe – Dưỡng sinh sau 50": {
        "mode": "single",
        "roles": [{"role": "all", "source": "provider", "voice": CHI}],
    },
    "Nhóm test": {
        "mode": "single",
        "roles": [{"role": "all", "source": "provider", "voice": CHI, "note": "Không dùng VieNeu"}],
    },
    "Topic Threads": {
        "mode": "multi",
        "roles": [
            {
                "role": "op",
                "source": "provider",
                "voices": [CHI, ADAM],
                "note": "Theo vibe: V1–V3 Chi, V4–V6 Adam",
            },
            {
                "role": "comment",
                "source": "provider",
                "voices": ["gemini:Puck", "gemini:Leda", "gemini:Sadachbia"],
                "note": "Xoay giọng giữa ElevenLabs và Gemini",
            },
        ],
        "rules": {"max_gemini_scenes": 2, "excited_tag": "Chỉ ElevenLabs, tối đa 1 lần mỗi video"},
    },
    "FoodDose": {
        "mode": "single",
        "roles": [
            {
                "role": "all",
                "source": "provider",
                "voice": ROGER,
                "volume": 100,
                "note": "Motion HTML canh nhịp theo Roger: đổi giọng thì soi lại khung hình sau render",
            }
        ],
    },
}


def upgrade() -> None:
    op.add_column(
        "knowledge_topics",
        sa.Column("voice_format", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("scenes", sa.Column("voice_name", sa.String(200), nullable=True))
    bind = op.get_bind()
    for name, voice_format in SEED.items():
        bind.execute(
            sa.text("UPDATE knowledge_topics SET voice_format = CAST(:format AS jsonb) WHERE name = :name"),
            {"format": json.dumps(voice_format, ensure_ascii=False), "name": name},
        )


def downgrade() -> None:
    op.drop_column("scenes", "voice_name")
    op.drop_column("knowledge_topics", "voice_format")
