"""videos, scenes, jobs and settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    empty_list = sa.text("'[]'::jsonb")
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("has_script", sa.Boolean(), nullable=False),
        sa.Column("title_options", JSONB(), server_default=empty_list, nullable=False),
        sa.Column("caption", sa.Text(), server_default="", nullable=False),
        sa.Column("hashtags", JSONB(), server_default=empty_list, nullable=False),
        sa.Column("affiliates", JSONB(), server_default=empty_list, nullable=False),
        sa.Column("pinned_comment", sa.Text(), server_default="", nullable=False),
        sa.Column("self_review", JSONB(), server_default=empty_list, nullable=False),
        sa.Column("music_suggestions", JSONB(), server_default=empty_list, nullable=False),
        sa.Column("thumbnail_key", sa.String(length=200), nullable=True),
        sa.Column("mp4_key", sa.String(length=200), nullable=True),
        sa.Column("mp4_seconds", sa.Float(), nullable=True),
        sa.Column("render_seconds", sa.Float(), nullable=True),
        sa.Column("rendered_signature", sa.String(length=64), nullable=True),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_videos_created_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_videos"),
    )
    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("is_title", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("seconds", sa.Float(), nullable=False),
        sa.Column("keywords", JSONB(), server_default=empty_list, nullable=False),
        sa.Column("image_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("image_key", sa.String(length=200), nullable=True),
        sa.Column("image_source", sa.Text(), nullable=True),
        sa.Column("image_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], name="fk_scenes_video_id_videos", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_scenes"),
    )
    op.create_index("ix_scenes_video_id", "scenes", ["video_id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("retry_of_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("claude_calls", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], name="fk_jobs_video_id_videos", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_jobs_created_by_id_users"),
        sa.ForeignKeyConstraint(["retry_of_id"], ["jobs.id"], name="fk_jobs_retry_of_id_jobs", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_video_id", "jobs", ["video_id"])
    op.create_index("ix_jobs_status_id", "jobs", ["status", "id"])
    # One queued or running job per video: the database itself refuses a duplicate Render.
    op.create_index(
        "uq_jobs_active_video", "jobs", ["video_id"], unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_settings_updated_by_id_users"),
        sa.PrimaryKeyConstraint("key", name="pk_settings"),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index("uq_jobs_active_video", table_name="jobs")
    op.drop_index("ix_jobs_status_id", table_name="jobs")
    op.drop_index("ix_jobs_video_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_scenes_video_id", table_name="scenes")
    op.drop_table("scenes")
    op.drop_table("videos")
