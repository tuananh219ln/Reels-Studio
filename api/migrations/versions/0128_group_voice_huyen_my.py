"""Groups 6, 7 and 10 ("Già Mà Khỏe", "Ăn Lành Sống Khỏe", "Nhóm test") read with VieNeu Huyền My in their
"Giọng đọc theo vai", not the ElevenLabs Chi that 0127 seeded (docs/decisions/2026-11-26-group-voice-huyen-my.md).

A group whose format a member has already edited on Kho kiến thức (it no longer equals 0127's seed) is left as it is.

Revision ID: 0128
Revises: 0127
Create Date: 2026-11-26
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None

CHI = "5yEPTrA0uAhZsBEhHjfi"
HUYEN_MY = "vieneu:Huyền My"
TEST_NOTE = "Giữ nguyên giọng gốc; chỉ đổi sang VieNeu Huyền My khi giọng gốc sai chuẩn"


def _single(voice: str, note: str = "") -> dict:
    role = {"role": "all", "source": "provider", "voice": voice}
    if note:
        role["note"] = note
    return {"mode": "single", "roles": [role]}


# name: (format 0127 seeded, format from now on)
CHANGES = {
    "Ăn Lành Sống Khỏe – Sức khỏe": (_single(CHI), _single(HUYEN_MY)),
    "Già Mà Khỏe – Dưỡng sinh sau 50": (_single(CHI), _single(HUYEN_MY)),
    "Nhóm test": (_single(CHI, "Không dùng VieNeu"), _single(HUYEN_MY, TEST_NOTE)),
}


def _swap(index_from: int) -> None:
    bind = op.get_bind()
    for name, formats in CHANGES.items():
        bind.execute(
            sa.text(
                "UPDATE knowledge_topics SET voice_format = CAST(:new AS jsonb) "
                "WHERE name = :name AND voice_format = CAST(:old AS jsonb)"
            ),
            {
                "name": name,
                "old": json.dumps(formats[index_from], ensure_ascii=False),
                "new": json.dumps(formats[1 - index_from], ensure_ascii=False),
            },
        )


def upgrade() -> None:
    _swap(0)


def downgrade() -> None:
    _swap(1)
