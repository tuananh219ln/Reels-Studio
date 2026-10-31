"""knowledge topics: prompts and banned words per topic

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from reels_api.knowledge import default_clone_prompt, default_script_prompt
from reels_api.script_rules import DEFAULT_BANNED_WORDS

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

FIRST_TOPIC = "Sức khỏe"


def upgrade() -> None:
    topics = op.create_table(
        "knowledge_topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("script_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("clone_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("banned_words", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_knowledge_topics_updated_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_topics"),
        sa.UniqueConstraint("name", name="uq_knowledge_topics_name"),
    )
    # Nullable with a default below, so a video the previous api creates during a deploy still gets a topic.
    op.add_column("videos", sa.Column("knowledge_topic_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_videos_knowledge_topic_id_knowledge_topics", "videos", "knowledge_topics", ["knowledge_topic_id"], ["id"]
    )

    # Everything so far belongs to the health channel. The settings rows stay, so a rollback still finds them.
    bind = op.get_bind()
    saved = dict(
        bind.execute(
            sa.text("SELECT key, value FROM settings WHERE key IN ('script_prompt', 'clone_prompt', 'banned_words')")
        ).all()
    )
    topic_id = bind.execute(
        sa.insert(topics)
        .returning(topics.c.id)
        .values(
            name=FIRST_TOPIC,
            script_prompt=saved.get("script_prompt", default_script_prompt()),
            clone_prompt=saved.get("clone_prompt", default_clone_prompt()),
            banned_words=saved.get("banned_words", list(DEFAULT_BANNED_WORDS)),
        )
    ).scalar_one()
    bind.execute(sa.text("UPDATE videos SET knowledge_topic_id = :id"), {"id": topic_id})
    bind.execute(sa.text(f"ALTER TABLE videos ALTER COLUMN knowledge_topic_id SET DEFAULT {int(topic_id)}"))


def downgrade() -> None:
    op.drop_constraint("fk_videos_knowledge_topic_id_knowledge_topics", "videos", type_="foreignkey")
    op.drop_column("videos", "knowledge_topic_id")
    op.drop_table("knowledge_topics")
