from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    false,
    func,
    text,
)
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


class McpClient(Base):
    __tablename__ = "mcp_clients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    redirect_uri: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class McpAuthorization(Base):
    __tablename__ = "mcp_authorizations"

    ticket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("mcp_clients.id", ondelete="CASCADE"))
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    challenge: Mapped[str] = mapped_column(String(128))
    resource: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class McpConnection(Base):
    __tablename__ = "mcp_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("mcp_clients.id", ondelete="CASCADE"))
    scopes: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(Text)
    access_hash: Mapped[str] = mapped_column(String(64), unique=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# A video is locked while it has one of these jobs; a partial unique index allows only one per video.
ACTIVE_JOB_STATUSES = ("queued", "running")


class KnowledgeTopic(Base):
    """One line of /knowledge: the prompts and banned words of the videos in this topic. Empty until written."""

    __tablename__ = "knowledge_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    script_prompt: Mapped[str] = mapped_column(Text, default="")
    clone_prompt: Mapped[str] = mapped_column(Text, default="")
    banned_words: Mapped[list] = mapped_column(JSONB, default=list)
    # The 30-day plan (plans.py): its prompt (empty: the default one), the date of day 1 in Vietnam, how many ideas
    # a day the AI is asked for, and the AI's last plan, kept for a member to look at before it replaces the plan.
    plan_prompt: Mapped[str] = mapped_column(Text, default="", server_default="")
    plan_start_date: Mapped[date | None] = mapped_column(Date)
    plan_per_day: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    plan_draft: Mapped[dict | None] = mapped_column(JSONB)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TopicPlanItem(Base):
    """One video idea of a topic group's 30-day plan. Its status comes from the linked video (plans.item_status), so
    it can never disagree with it; deleting the video unlinks it."""

    __tablename__ = "topic_plan_items"
    __table_args__ = (
        CheckConstraint("day BETWEEN 1 AND 30", name="day"),
        Index("ix_topic_plan_items_knowledge_topic_id_day", "knowledge_topic_id", "day", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_topic_id: Mapped[int] = mapped_column(ForeignKey("knowledge_topics.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)  # 1-5 within the day
    topic: Mapped[str] = mapped_column(Text)  # becomes the video's Chủ đề
    pain_group: Mapped[str] = mapped_column(String(100), default="", server_default="")
    pain: Mapped[str] = mapped_column(Text, default="", server_default="")
    hook: Mapped[str] = mapped_column(Text, default="", server_default="")
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), unique=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    knowledge_topic_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_topics.id"))
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
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # The video's own settings (video_options.DEFAULTS keys); None renders the original template.
    options: Mapped[dict | None] = mapped_column(JSONB)
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
    # The same search terms in English: Western stock libraries (Pixabay, Pexels) index in English,
    # so their searches use these; the Vietnamese list stays for Openverse and for display.
    keywords_en: Mapped[list] = mapped_column(JSONB, default=list)
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    image_key: Mapped[str | None] = mapped_column(String(200))
    # "upload" or the Pixabay URL the image came from: "Tìm lại ảnh" must pick a different one.
    image_source: Mapped[str | None] = mapped_column(Text)
    image_error: Mapped[str | None] = mapped_column(Text)
    # Picked by the app after the script ("Tự tìm ảnh"): shown as "Tự chọn, kiểm tra lại" until the photo changes.
    image_auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    voice_text: Mapped[str] = mapped_column(Text, default="")
    # The last narration MP3 made for this scene and the tts.voice_signature it was made from: it is reused
    # while the signature still matches, so a re-render does not pay ElevenLabs again.
    voice_key: Mapped[str | None] = mapped_column(String(200))
    voice_signature: Mapped[str | None] = mapped_column(String(64))
    voice_seconds: Mapped[float | None] = mapped_column(Float)
    # A clip shown instead of the photo: a scene has one or the other, never both.
    video_key: Mapped[str | None] = mapped_column(String(200))
    video_seconds: Mapped[float | None] = mapped_column(Float)  # the clip's probed length
    video_start: Mapped[float] = mapped_column(Float, default=0)
    video_speed: Mapped[float] = mapped_column(Float, default=1)
    # Where a member dragged the text box (its centre in the 1080×1920 frame); None: the video's place for its
    # scenes, else the template's. The renderer keeps the box inside the platforms' safe zone.
    text_x: Mapped[int | None] = mapped_column(Integer)
    text_y: Mapped[int | None] = mapped_column(Integer)

    video: Mapped[Video] = relationship(back_populates="scenes")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index(
            "uq_jobs_active_video", "video_id", unique=True, postgresql_where=text("status IN ('queued', 'running')")
        ),
        Index("ix_jobs_status_id", "status", "id"),
        Index(
            "uq_jobs_active_plan",
            "knowledge_topic_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND kind = 'plan'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Every job belongs to a video, except a plan job ("Tạo bằng AI" on /knowledge), which belongs to a topic group.
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    knowledge_topic_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_topics.id", ondelete="CASCADE"))
    # script | clone | render | publish | unpublish | check | image | photos | voice | plan
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed | cancelled
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    # An image job for one scene ("Tạo ảnh AI" on its card); None: every scene without a photo or clip.
    scene_id: Mapped[int | None] = mapped_column(Integer)
    # The AI image provider of an image job ("cloudflare" | "gemini"), fixed when it is queued.
    image_provider: Mapped[str | None] = mapped_column(String(16))
    publication_id: Mapped[int | None] = mapped_column(Integer)  # The post an unpublish job takes down.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    claude_calls: Mapped[int] = mapped_column(Integer, default=0)
    image_calls: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Gemini calls of an image job, counted like claude_calls
    # The LLM a script or clone job wrote with (llm.py's provider id and the model name); claude_calls counts its calls.
    llm_provider: Mapped[str | None] = mapped_column(String(32))
    llm_model: Mapped[str | None] = mapped_column(String(200))

    created_by: Mapped[User] = relationship()


class Fanpage(Base):
    """A Facebook Page connected on /fanpages. `token_encrypted` is the Page's own token (see fanpages.py)."""

    __tablename__ = "fanpages"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    token_encrypted: Mapped[str] = mapped_column(Text)
    token_tail: Mapped[str] = mapped_column(String(8))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    updated_by: Mapped[User | None] = relationship()


class LlmProvider(Base):
    """A provider's settings from /settings/ai; the list of providers is fixed in llm.py. The key is encrypted
    like a Fanpage token (see crypto.py) and empty fields fall back to the provider's defaults."""

    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    key_encrypted: Mapped[str | None] = mapped_column(Text)
    key_tail: Mapped[str | None] = mapped_column(String(8))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    updated_by: Mapped[User | None] = relationship()


class AppSetting(Base):
    """A team-wide setting from the Cài đặt pages, by key (e.g. "llm_provider")."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Publication(Base):
    """One post of a video to a platform; a video posted again has one row per post, kept after it is cancelled or
    deleted. The publish job reads what to do from the video's one pending row."""

    __tablename__ = "publications"
    __table_args__ = (
        Index(
            "uq_publications_pending", "video_id", "platform", unique=True, postgresql_where=text("status = 'pending'")
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(16))  # facebook
    fanpage_id: Mapped[int | None] = mapped_column(ForeignKey("fanpages.id"))
    # pending | scheduled | published | cancelled (never went live) | deleted (taken off the platform after going live)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The platform's id, saved before the upload, so "Thử lại" continues this reel instead of posting a second one.
    remote_id: Mapped[str | None] = mapped_column(String(64))
    remote_mp4_key: Mapped[str | None] = mapped_column(String(200))  # the MP4 sent as `remote_id`
    # Set before Facebook is asked to publish `remote_id`: from then on it may go live even if the answer was lost.
    finish_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # when it was cancelled or deleted
    # None when the reel was found gone or stopped on Facebook by a check, not taken down from the app.
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # When a check last read the reel on Facebook, or was queued to: one automatic check per scheduled time.
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fanpage: Mapped[Fanpage | None] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    closed_by: Mapped[User | None] = relationship(foreign_keys=[closed_by_id])


class MusicTrack(Base):
    """A track in the team library. Choosing it for a video copies the file into the video's folder, so editing
    or deleting the track never changes a video."""

    __tablename__ = "music_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    topics: Mapped[list] = mapped_column(JSONB, default=list)  # values from music.TOPICS
    mood: Mapped[str] = mapped_column(String(40))  # a value from music.MOODS
    license_note: Mapped[str] = mapped_column(Text, default="")
    storage_key: Mapped[str] = mapped_column(String(200))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped[User] = relationship()


class AffiliateProduct(Base):
    """A Shopee product the team may promote, with the figures a member copied from the affiliate dashboard.
    Rows start as drafts; only a member's approval makes one usable, and changing an approved row undoes that."""

    __tablename__ = "affiliate_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_topic_id: Mapped[int] = mapped_column(ForeignKey("knowledge_topics.id"))
    name: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(Text)  # the affiliate link
    shop_name: Mapped[str] = mapped_column(String(200))
    shop_type: Mapped[str] = mapped_column(String(16))  # a key of routes_affiliate.SHOP_TYPES
    rating: Mapped[float] = mapped_column(Float)
    sold: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)  # VND
    commission_rate: Mapped[float] = mapped_column(Float)  # percent
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | approved
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topic: Mapped[KnowledgeTopic] = relationship()
    checked_by: Mapped[User | None] = relationship(foreign_keys=[checked_by_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])


class VideoAffiliateProduct(Base):
    """A product whose link goes in the pinned comment of a posted reel."""

    __tablename__ = "video_affiliate_products"

    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("affiliate_products.id", ondelete="CASCADE"), primary_key=True)


class Setting(Base):
    """The prompts and banned words before knowledge_topics; no longer read, kept so a rollback finds them."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VideoPresence(Base):
    """One open video page ("tab": a random id the page picks when it opens), so members see who else is on the
    video and whether they are editing. Rows silent for longer than routes_presence.TIMEOUT are deleted."""

    __tablename__ = "video_presence"

    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    tab: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    editing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
