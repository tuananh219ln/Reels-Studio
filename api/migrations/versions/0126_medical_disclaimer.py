"""A topic group's medical reminder moves from the caption to the last pinned comment (disclaimer.py).

Health groups (a name with "khỏe") get it switched on; the scripts of those groups that no article was made from lose
the reminder from their body (the sentence is written under the post now). Posted articles and drafts are left alone:
the caption is cleaned when it is posted.

Revision ID: 0126
Revises: 0125
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_topics",
        sa.Column("medical_disclaimer_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "knowledge_topics", sa.Column("medical_disclaimer_text", sa.Text(), server_default="", nullable=False)
    )
    op.add_column(
        "knowledge_topics",
        sa.Column("medical_disclaimer_position", sa.String(16), server_default="last_comment", nullable=False),
    )
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE knowledge_topics SET medical_disclaimer_enabled = true WHERE name ILIKE '%khỏe%'"))

    from reels_api import disclaimer

    rows = bind.execute(
        sa.text(
            "SELECT s.id, s.body FROM article_plan_slots s JOIN knowledge_topics t ON t.id = s.knowledge_topic_id "
            "WHERE t.medical_disclaimer_enabled AND s.article_id IS NULL"
        )
    ).all()
    for slot_id, body in rows:
        cleaned = disclaimer.strip(body or "")
        if cleaned != (body or "").strip():
            bind.execute(
                sa.text("UPDATE article_plan_slots SET body = :body WHERE id = :id"), {"body": cleaned, "id": slot_id}
            )


def downgrade() -> None:
    op.drop_column("knowledge_topics", "medical_disclaimer_position")
    op.drop_column("knowledge_topics", "medical_disclaimer_text")
    op.drop_column("knowledge_topics", "medical_disclaimer_enabled")
