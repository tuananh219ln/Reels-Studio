from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, MetaData, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)  # always stored normalized (lowercase)
    name: Mapped[str] = mapped_column(String(60))
    password_hash: Mapped[str] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


# A video is locked while it has one of these jobs; a partial unique index allows only one per video.
ACTIVE_JOB_STATUSES = ("queued", "running")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    has_script: Mapped[bool] = mapped_column(Boolean, default=False)
    title_options: Mapped[list] = mapped_column(JSONB, default=list)
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSONB, default=list)
    affiliates: Mapped[list] = mapped_column(JSONB, default=list)
    pinned_comment: Mapped[str] = mapped_column(Text, default="")
    self_review: Mapped[list] = mapped_column(JSONB, default=list)
    music_suggestions: Mapped[list] = mapped_column(JSONB, default=list)
    thumbnail_key: Mapped[str | None] = mapped_column(String(200))
    mp4_key: Mapped[str | None] = mapped_column(String(200))
    mp4_seconds: Mapped[float | None] = mapped_column(Float)
    render_seconds: Mapped[float | None] = mapped_column(Float)
    # Fingerprint of everything that changes the MP4, taken at render time (see videos.render_signature).
    rendered_signature: Mapped[str | None] = mapped_column(String(64))
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    music_key: Mapped[str | None] = mapped_column(String(200))
    music_name: Mapped[str | None] = mapped_column(String(200))  # the uploaded file's name, display only
    music_volume: Mapped[int] = mapped_column(Integer, default=25)  # percent
    # Snapshot taken when "Nhân bản" was pressed: the source's title, topic, edited script and the change
    # request. A clone draft keeps it, so cancelling and writing again reruns the same clone.
    clone_source: Mapped[dict | None] = mapped_column(JSONB)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped[User] = relationship()
    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="video", order_by="(Scene.is_title.desc(), Scene.position, Scene.id)", passive_deletes=True
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    is_title: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    seconds: Mapped[float] = mapped_column(Float)
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    image_key: Mapped[str | None] = mapped_column(String(200))
    # "upload" or the Pixabay URL the image came from: "Tìm lại ảnh" must pick a different one.
    image_source: Mapped[str | None] = mapped_column(Text)
    image_error: Mapped[str | None] = mapped_column(Text)

    video: Mapped[Video] = relationship(back_populates="scenes")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("uq_jobs_active_video", "video_id", unique=True,
              postgresql_where=text("status IN ('queued', 'running')")),
        Index("ix_jobs_status_id", "status", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # script | clone | render
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed | cancelled
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    claude_calls: Mapped[int] = mapped_column(Integer, default=0)

    created_by: Mapped[User] = relationship()


class Setting(Base):
    """Editable app data (script prompt, banned words); a missing row means the default from code."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
