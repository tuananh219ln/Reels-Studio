"""the 30-day topic plan of a topic group, and jobs that belong to a topic group instead of a video

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Defaulted columns, so the previous api version keeps working during a deploy.
    op.add_column("knowledge_topics", sa.Column("plan_prompt", sa.Text(), server_default="", nullable=False))
    op.add_column("knowledge_topics", sa.Column("plan_start_date", sa.Date(), nullable=True))
    op.add_column("knowledge_topics", sa.Column("plan_per_day", sa.Integer(), server_default="4", nullable=False))
    op.add_column("knowledge_topics", sa.Column("plan_draft", postgresql.JSONB(), nullable=True))

    op.create_table(
        "topic_plan_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_topic_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("pain_group", sa.String(length=100), server_default="", nullable=False),
        sa.Column("pain", sa.Text(), server_default="", nullable=False),
        sa.Column("hook", sa.Text(), server_default="", nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # op.f: the name is final; the naming convention would otherwise prefix it a second time.
        sa.CheckConstraint("day BETWEEN 1 AND 30", name=op.f("ck_topic_plan_items_day")),
        sa.ForeignKeyConstraint(
            ["knowledge_topic_id"],
            ["knowledge_topics.id"],
            name="fk_topic_plan_items_knowledge_topic_id_knowledge_topics",
            ondelete="CASCADE",
        ),
        # Deleting the video sends its idea back to "Ý tưởng".
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name="fk_topic_plan_items_video_id_videos", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_topic_plan_items_updated_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_topic_plan_items"),
        sa.UniqueConstraint("video_id", name="uq_topic_plan_items_video_id"),
    )
    op.create_index(
        "ix_topic_plan_items_knowledge_topic_id_day", "topic_plan_items", ["knowledge_topic_id", "day", "position"]
    )

    # A plan job ("Tạo bằng AI") belongs to a topic group, not to a video.
    op.alter_column("jobs", "video_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("jobs", sa.Column("knowledge_topic_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_knowledge_topic_id_knowledge_topics",
        "jobs",
        "knowledge_topics",
        ["knowledge_topic_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_jobs_active_plan",
        "jobs",
        ["knowledge_topic_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running') AND kind = 'plan'"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE video_id IS NULL")
    op.drop_index("uq_jobs_active_plan", table_name="jobs")
    op.drop_constraint("fk_jobs_knowledge_topic_id_knowledge_topics", "jobs", type_="foreignkey")
    op.drop_column("jobs", "knowledge_topic_id")
    op.alter_column("jobs", "video_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_topic_plan_items_knowledge_topic_id_day", table_name="topic_plan_items")
    op.drop_table("topic_plan_items")
    op.drop_column("knowledge_topics", "plan_draft")
    op.drop_column("knowledge_topics", "plan_per_day")
    op.drop_column("knowledge_topics", "plan_start_date")
    op.drop_column("knowledge_topics", "plan_prompt")
