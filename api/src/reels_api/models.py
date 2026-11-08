from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
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
    UniqueConstraint,
    false,
    func,
    text,
    true,
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


class RenderNode(Base):
    """A member's own computer that renders for the team (render_nodes.py), known by a token shown once."""

    __tablename__ = "render_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped["User"] = relationship()


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
    # The callback this grant goes back to: one the client registered (a loopback one on this session's port).
    # Empty on grants made before Claude could connect, which used the client's only callback.
    redirect_uri: Mapped[str] = mapped_column(Text, server_default="")
    code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    client: Mapped[McpClient] = relationship()


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

    client: Mapped[McpClient] = relationship()


# A video is locked while it has one of these jobs; a partial unique index allows only one per video.
ACTIVE_JOB_STATUSES = ("queued", "running")


DEFAULT_POST_TIMES = ("07:00", "11:30", "17:00", "20:00", "21:30")
DEFAULT_POST_TIMES_SQL = '\'["07:00", "11:30", "17:00", "20:00", "21:30"]\'::jsonb'


class KnowledgeTopic(Base):
    """One line of /knowledge: the prompts and banned words of the videos in this topic. Empty until written."""

    __tablename__ = "knowledge_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    script_prompt: Mapped[str] = mapped_column(Text, default="")
    clone_prompt: Mapped[str] = mapped_column(Text, default="")
    # "Nhờ AI sửa" (the studio's notes): empty uses prompts/revise_default.txt.
    revise_prompt: Mapped[str] = mapped_column(Text, default="", server_default="")
    banned_words: Mapped[list] = mapped_column(JSONB, default=list)
    # "Gợi ý tìm ảnh": what the group's photos show (growing plants, not cooked dishes...), added to the script and
    # clone prompts so the AI writes the scenes' search keywords and image prompts for it. Empty: nothing added.
    photo_hint: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The group's own narration voice (an ElevenLabs id or "vieneu:<id>"): a new video of the group starts with it,
    # over its maker's defaults (video_options.apply_defaults). Empty: the maker's defaults decide.
    voice_id: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # "Từ video mẫu" (reference.py): the prompt that writes a script from a sample video, and the one that analyses
    # the sample on its own (ways B, C and D). Empty: the default in prompts/.
    learn_prompt: Mapped[str] = mapped_column(Text, default="", server_default="")
    analyze_prompt: Mapped[str] = mapped_column(Text, default="", server_default="")
    # "Prompt viết bài" (articles.py): the caption of an article ("Bài viết"). Empty: prompts/article_default.txt.
    article_prompt: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The 30-day plan (plans.py): its prompt (empty: the default one), the date of day 1 in Vietnam, how many ideas
    # a day the AI is asked for, and the AI's last plan, kept for a member to look at before it replaces the plan.
    plan_prompt: Mapped[str] = mapped_column(Text, default="", server_default="")
    plan_start_date: Mapped[date | None] = mapped_column(Date)
    plan_per_day: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    plan_draft: Mapped[dict | None] = mapped_column(JSONB)
    # "HH:MM" in Vietnam: the n-th idea of a plan day is suggested to be posted at the n-th time.
    plan_post_times: Mapped[list] = mapped_column(
        JSONB, default=lambda: list(DEFAULT_POST_TIMES), server_default=text(DEFAULT_POST_TIMES_SQL)
    )
    # How many videos the group's trial counts towards ("Tiến độ verdict" on its plan); None: no banner. Only a count:
    # the verdict itself is decided by the team in a meeting.
    video_target: Mapped[int | None] = mapped_column(Integer)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TopicPlanItem(Base):
    """One video idea of a topic group's 30-day plan, or of its Backlog when it has no day. Its status comes from the
    linked video and its posts (plans.item_status), so it can never disagree with them; deleting the video unlinks
    it."""

    __tablename__ = "topic_plan_items"
    __table_args__ = (
        CheckConstraint("day IS NULL OR day BETWEEN 1 AND 30", name="day"),
        Index("ix_topic_plan_items_knowledge_topic_id_day", "knowledge_topic_id", "day", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_topic_id: Mapped[int] = mapped_column(ForeignKey("knowledge_topics.id", ondelete="CASCADE"))
    day: Mapped[int | None] = mapped_column(Integer)  # None: in the Backlog
    position: Mapped[int] = mapped_column(Integer)  # 1-5 within the day; any number in the Backlog
    topic: Mapped[str] = mapped_column(Text)  # becomes the video's Chủ đề
    pain_group: Mapped[str] = mapped_column(String(100), default="", server_default="")
    pain: Mapped[str] = mapped_column(Text, default="", server_default="")
    hook: Mapped[str] = mapped_column(Text, default="", server_default="")
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), unique=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VideoReference(Base):
    """A sample video members learn from ("Từ video mẫu", reference.py): its file stays stored so scene clips can be
    cut from it, by any number of videos. `frames` are the stills the AI looks at: [{"second", "key", "note"}], the
    note written by the analysis. `analysis` is empty until the AI analysed it; members may edit it."""

    __tablename__ = "video_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str | None] = mapped_column(Text)  # None: an uploaded file
    source_name: Mapped[str] = mapped_column(String(300))  # the link or the uploaded file's name, display only
    video_key: Mapped[str | None] = mapped_column(String(200))  # None until a link is downloaded by the job
    seconds: Mapped[float | None] = mapped_column(Float)
    transcript: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The same words with their seconds, [{"text", "start", "end"}]: "Edit từ footage" cuts and captions by them.
    words: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    frames: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    analysis: Mapped[str] = mapped_column(Text, default="", server_default="")
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped[User] = relationship()


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    knowledge_topic_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_topics.id"))
    has_script: Mapped[bool] = mapped_column(Boolean, default=False)
    # "Tự viết": a member wrote the script, so no AI wrote it and none reviewed its safety.
    hand_written: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # "assistant": the script was written by a member's own Claude through MCP (on their plan, at no cost to the
    # team's AI service); "": by the team's AI service in a job, or typed by a member.
    written_via: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # Which assistant wrote it through MCP (mcp_auth.app_of: ChatGPT, Claude, Claude Code, Muse); "" when unknown
    # (made before this was kept) or not written through MCP.
    assistant_app: Mapped[str] = mapped_column(String(20), default="", server_default="")
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
    # The MP4's automatic QC (qc.py), measured by the render job that made it: {"status", "checks": [...]}.
    qc: Mapped[dict | None] = mapped_column(JSONB)
    render_seconds: Mapped[float | None] = mapped_column(Float)
    # Fingerprint of everything that changes the MP4, taken at render time (see videos.render_signature).
    rendered_signature: Mapped[str | None] = mapped_column(String(64))
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    music_key: Mapped[str | None] = mapped_column(String(200))
    music_name: Mapped[str | None] = mapped_column(String(200))  # the uploaded file's name, display only
    music_volume: Mapped[int] = mapped_column(Integer, default=25)  # percent
    # "AI gợi ý hiệu ứng" when the video was made: its script call also picks each scene's effects.
    ai_effects: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Where in the song the video's music starts, in seconds ("Bài nhạc bắt đầu từ giây").
    music_start: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # The video's own settings (video_options.DEFAULTS keys); None renders the original template.
    options: Mapped[dict | None] = mapped_column(JSONB)
    # Snapshot taken when "Nhân bản" was pressed: the source's title, topic, edited script and the change
    # request. A clone draft keeps it, so cancelling and writing again reruns the same clone.
    clone_source: Mapped[dict | None] = mapped_column(JSONB)
    # "Từ video mẫu": the sample video the script is learned from and the way it was asked for (reference.MODES:
    # quick, twostep, review, reuse). Deleting the sample keeps the video and its clips.
    reference_id: Mapped[int | None] = mapped_column(ForeignKey("video_references.id", ondelete="SET NULL"), index=True)
    reference_mode: Mapped[str | None] = mapped_column(String(16))
    # Where the video is made for: facebook (a Reel, Shopee links) or tiktok (posted by hand, TikTok Shop's cart). A
    # TikTok version is its own video, cloned from the Facebook one it names in `variant_of_id`.
    platform: Mapped[str] = mapped_column(String(16), default="facebook", server_default="facebook")
    # How the video is built (videos.MODES): "slides", each scene over its own photo or clip; "single" ("Video xuyên
    # suốt"), the title scene's photo or clip under every scene, a scene's own photo shown only as its photo layer.
    # Switching keeps every photo, clip and layer, so switching back loses nothing.
    mode: Mapped[str] = mapped_column(String(16), default="slides", server_default="slides")
    # "Loại nội dung": what kind of content a member says it is (Hướng dẫn, Mẹo nhanh...), free text; "" for none.
    content_type: Mapped[str] = mapped_column(String(40), default="", server_default="")
    variant_of_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"))
    # Shopee product suggestions (affiliate_suggest.py): asked for, with whose account, done, and what went wrong.
    suggest_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suggest_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    suggested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suggest_error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
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
    # "Tự khớp lời đọc": once its narration is made, the scene lasts as long as it (videos.auto_seconds). Typing the
    # seconds turns it off. The scenes the app writes (script, "Tự viết", "Thêm cảnh") start on; older ones off.
    seconds_auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
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
    # "Sửa ảnh" (image_edit.py): the photo the scene had before its first edit, so "Khôi phục ảnh gốc" brings it back.
    # None for a photo never edited; any new photo, clip or removal drops it (videos.drop_original).
    image_original_key: Mapped[str | None] = mapped_column(String(200))
    # "Tìm chữ/logo tự động" (image_marks job): {"key": the photo it looked at, "boxes": [[x, y, w, h], ...]}, offered
    # as boxes in "Xóa vùng" while the scene still shows that photo.
    image_marks: Mapped[dict | None] = mapped_column(JSONB)
    # "Làm mờ vùng" on a clip: {"key": the clip, "boxes": [[x, y, w, h], ...]} as fractions of the 1080x1920 frame,
    # blurred for the whole scene (reels_render/blur.py) while the scene still shows that clip.
    video_blur: Mapped[dict | None] = mapped_column(JSONB)
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
    # "Tiếng gốc": the clip's own sound is heard in the render ("Edit từ footage" turns it on); off, it is left out.
    video_sound: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # What the clip's sound says, [{"text", "start", "end"}] in the clip's own seconds (ElevenLabs Speech-to-Text):
    # captions follow these real times. None for every other clip; any new clip drops them.
    words: Mapped[list | None] = mapped_column(JSONB)
    # Where a member dragged the text box (its centre in the 1080×1920 frame); None: the video's place for its
    # scenes, else the template's. The renderer keeps the box inside the platforms' safe zone.
    text_x: Mapped[int | None] = mapped_column(Integer)
    text_y: Mapped[int | None] = mapped_column(Integer)
    # The studio's per-scene effects (reels_render.effects): the transition into this scene, None for the video's;
    # its colour preset, None for the picture as shot. The title scene has neither.
    transition: Mapped[str | None] = mapped_column(String(16))
    color: Mapped[str | None] = mapped_column(String(24))
    # The music's level during this scene (reels_render.sounds.MUSIC_LEVELS); None: the video's.
    music_level: Mapped[str | None] = mapped_column(String(8))
    # A "Cảnh động" (motion.py): HyperFrames markup an assistant wrote, rendered by the worker into the scene's clip.
    # {"html", "seconds", "photo_key": a copy of the scene's photo the markup may show, "clip_key": the clip it
    # made}. The scene shows it while video_key is still clip_key; another photo or clip simply takes its place.
    motion: Mapped[dict | None] = mapped_column(JSONB)

    video: Mapped[Video] = relationship(back_populates="scenes")
    layers: Mapped[list["SceneLayer"]] = relationship(
        back_populates="scene", order_by="SceneLayer.position", cascade="all, delete-orphan", passive_deletes=True
    )
    sounds: Mapped[list["SceneSound"]] = relationship(
        back_populates="scene", order_by="SceneSound.id", cascade="all, delete-orphan", passive_deletes=True
    )


class SceneSound(Base):
    """A sound effect heard from a second of its scene (reels_render.sounds), added in the studio."""

    __tablename__ = "scene_sounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    sound: Mapped[str] = mapped_column(String(24))
    start: Mapped[float] = mapped_column(Float, default=0)  # seconds into the scene
    volume: Mapped[str] = mapped_column(String(8), default="normal")

    scene: Mapped[Scene] = relationship(back_populates="sounds")


class SceneLayer(Base):
    """A text or sticker layer over a scene for its own seconds (reels_render.layers), added in the studio."""

    __tablename__ = "scene_layers"

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)  # laid on in this order, the last on top
    kind: Mapped[str] = mapped_column(String(8))  # "text" | "sticker" | "photo"
    text: Mapped[str] = mapped_column(Text, default="")
    sticker: Mapped[str] = mapped_column(String(24), default="")
    start: Mapped[float] = mapped_column(Float, default=0)  # seconds into the scene
    seconds: Mapped[float] = mapped_column(Float, default=2)
    x: Mapped[int] = mapped_column(Integer, default=540)  # its centre in the 1080×1920 frame
    y: Mapped[int] = mapped_column(Integer, default=960)
    size: Mapped[str] = mapped_column(String(8), default="medium")
    style: Mapped[str] = mapped_column(String(16), default="outline")
    animation: Mapped[str] = mapped_column(String(16), default="fade")

    scene: Mapped[Scene] = relationship(back_populates="layers")


class EditTemplate(Base):
    """A team's "Mẫu dựng", saved from a video it likes (autoedit.Template as JSON)."""

    __tablename__ = "edit_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    data: Mapped[dict] = mapped_column(JSONB)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VideoNote(Base):
    """A member's comment at a second of the video ("Góp ý" in the studio), sent to the AI with "Nhờ AI sửa"."""

    __tablename__ = "video_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    at: Mapped[float] = mapped_column(Float)  # seconds from the video's start
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8), default="open")  # open | sent (to a revise job) | done
    reply: Mapped[str] = mapped_column(Text, default="")  # the AI's answer once done
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index(
            "uq_jobs_active_video", "video_id", unique=True, postgresql_where=text("status IN ('queued', 'running')")
        ),
        Index("ix_jobs_status_id", "status", "id"),
        Index(
            "uq_jobs_active_article",
            "article_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index(
            "uq_jobs_active_plan",
            "knowledge_topic_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND kind = 'plan'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Every job belongs to a video, except a plan job ("Tạo bằng AI" on /knowledge), which belongs to a topic group,
    # and an article_caption job, which belongs to an article.
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    knowledge_topic_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_topics.id", ondelete="CASCADE"))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    # script | clone | learn | render | publish | unpublish | check | image | photos | voice | plan | revise
    # | article_caption | motion | tiktok_publish | image_edit | image_marks
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed | cancelled
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    # An image job for one scene ("Tạo ảnh AI" on its card); None: every scene without a photo or clip.
    scene_id: Mapped[int | None] = mapped_column(Integer)
    # The AI image provider of an image job ("cloudflare" | "gemini"), fixed when it is queued.
    image_provider: Mapped[str | None] = mapped_column(String(16))
    # An image_edit job ("Sửa ảnh"): its engine is in image_provider ("lama" | "cloudflare" | "gemini"), the boxes a
    # member drew as [x, y, width, height] fractions of the photo, and what they asked for in words.
    edit_boxes: Mapped[list | None] = mapped_column(JSONB)
    edit_prompt: Mapped[str | None] = mapped_column(Text)
    # The post an unpublish job takes down, or the TikTok post a tiktok_publish job sends.
    publication_id: Mapped[int | None] = mapped_column(Integer)
    # A render or motion job handed to a member's render machine (render_nodes.py): "ready" once the VPS has packed
    # what it needs, "taken" while a machine renders it; None for a job the worker runs itself. The job stays
    # `running` meanwhile, so the video stays locked and the worker's restart and exit checks leave it alone.
    node_stage: Mapped[str | None] = mapped_column(String(8))
    node_id: Mapped[int | None] = mapped_column(ForeignKey("render_nodes.id", ondelete="SET NULL"))
    node_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the machine's last word on it
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
    # The worker's last check of the token (fanpages.check): when, what went wrong (None when it worked), when a member
    # asked for one with "Kiểm tra ngay", and the Page's followers it read.
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_error: Mapped[str | None] = mapped_column(Text)
    check_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followers_count: Mapped[int | None] = mapped_column(Integer)
    # What went wrong reading the Page's daily numbers at the last check (fanpages.read_insights), None when it worked.
    insights_error: Mapped[str | None] = mapped_column(Text)
    # The member whose Page it is: only they set its Shopee account, whose links its comments carry.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    shopee_account_id: Mapped[int | None] = mapped_column(ForeignKey("affiliate_accounts.id", ondelete="SET NULL"))
    # The one topic group the Page posts; its queue takes its owner's videos of that group (page_queue.py).
    knowledge_topic_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_topics.id", ondelete="SET NULL"))
    # "HH:MM" in Vietnam, when its queue posts; None: the group's posting times.
    post_times: Mapped[list | None] = mapped_column(JSONB)

    updated_by: Mapped[User | None] = relationship(foreign_keys=[updated_by_id])
    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])


class PageQueueItem(Base):
    """A rendered video waiting in a Page's queue: the worker gives the first one the Page's next free posting time and
    schedules it on Facebook (page_queue.py). The row goes once the post is made; one it could not post keeps why."""

    __tablename__ = "page_queue_items"
    __table_args__ = (
        Index("uq_page_queue_items_video_id", "video_id", unique=True),
        Index("ix_page_queue_items_fanpage_id_position", "fanpage_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fanpage_id: Mapped[int] = mapped_column(ForeignKey("fanpages.id", ondelete="CASCADE"))
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    auto_comment: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    added_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    fanpage: Mapped[Fanpage] = relationship()
    video: Mapped[Video] = relationship()
    added_by: Mapped[User] = relationship()


class FanpageFollowers(Base):
    """A Page's followers on one day (Vietnam time), the last number read that day, for the gain of a week."""

    __tablename__ = "fanpage_followers"
    __table_args__ = (Index("uq_fanpage_followers_fanpage_id_day", "fanpage_id", "day", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fanpage_id: Mapped[int] = mapped_column(ForeignKey("fanpages.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    followers: Mapped[int] = mapped_column(Integer)


class FanpageInsights(Base):
    """A Page's numbers for one day (Vietnam time) from Page Insights, read by the worker's check: views of its content,
    the people reached and the engagements on its posts; None when Facebook gave no number."""

    __tablename__ = "fanpage_insights"
    __table_args__ = (Index("uq_fanpage_insights_fanpage_id_day", "fanpage_id", "day", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fanpage_id: Mapped[int] = mapped_column(ForeignKey("fanpages.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    views: Mapped[int | None] = mapped_column(Integer)
    reach: Mapped[int | None] = mapped_column(Integer)
    engagements: Mapped[int | None] = mapped_column(Integer)


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


class UserVideoDefaults(Base):
    """A member's own "Thiết lập mặc định": every setting their new videos start with, the team's (AppSetting
    "video_defaults") copied when they first saved their own and changed since. No row: the team's apply."""

    __tablename__ = "user_video_defaults"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserLastChoices(Base):
    """What a member last picked where a form asks for a Page or a topic group (brief part B3): the forms start on it,
    each member on their own. A removed Page or group leaves the choice empty."""

    __tablename__ = "user_last_choices"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    fanpage_id: Mapped[int | None] = mapped_column(ForeignKey("fanpages.id", ondelete="SET NULL"))
    knowledge_topic_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_topics.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
    """One post of a video, or of an article ("Bài viết"), to a platform; posted again, it has one row per post, kept
    after it is cancelled or deleted. The publish job reads what to do from the one pending row. Code that lists every
    post and reads its video must keep to `video_id IS NOT NULL` (articles.py has the articles' side)."""

    __tablename__ = "publications"
    __table_args__ = (
        Index(
            "uq_publications_pending", "video_id", "platform", unique=True, postgresql_where=text("status = 'pending'")
        ),
        Index(
            "uq_publications_pending_article",
            "article_id",
            "platform",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_publications_article_id", "article_id"),
        CheckConstraint("(video_id IS NULL) <> (article_id IS NULL)", name="one_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    # An article's text as sent (caption, product line, hashtags), so a retry after a lost answer finds that very post.
    post_text: Mapped[str | None] = mapped_column(Text)
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
    # The worker's last reading of the reel's numbers (metrics.py), and what went wrong with it; None once one works.
    metrics_tried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics_error: Mapped[str | None] = mapped_column(Text)
    # "Cập nhật view": the worker reads the numbers in its next round, even for a post past the days it follows.
    metrics_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The affiliate comment the worker writes under the reel once it is live (post_comments.py). Only posts made with
    # "Tự bình luận" on get one by themselves; `comment_id` is Facebook's, so the comment is edited, never posted twice.
    auto_comment: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    comment_id: Mapped[str | None] = mapped_column(String(64))
    comment_text: Mapped[str | None] = mapped_column(Text)  # what was sent last
    comment_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set before asking Facebook
    commented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # Facebook took it
    comment_error: Mapped[str | None] = mapped_column(Text)
    comment_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # "Bình luận ngay"
    # When the worker last read the visitors' comments under the reel (comments_inbox.py), and what went wrong then.
    comments_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comments_error: Mapped[str | None] = mapped_column(Text)
    # Where each scene starts and ends in the MP4 sent as `remote_id` ({label, start, end} in seconds), taken when it
    # was uploaded, so the retention curve is read against the scenes that were posted, not later edits.
    scene_marks: Mapped[list | None] = mapped_column(JSONB)
    # A TikTok post, made by hand in TikTok's app and recorded with its link, or sent through TikTok's API (`remote_id`
    # is then TikTok's publish_id): the member's TikTok account and the link, which a member adds once it is posted.
    affiliate_account_id: Mapped[int | None] = mapped_column(ForeignKey("affiliate_accounts.id", ondelete="SET NULL"))
    post_url: Mapped[str | None] = mapped_column(Text)
    # A TikTok post sent through the API: "draft" (to the member's TikTok inbox) or "direct"; None for any other post.
    publish_mode: Mapped[str | None] = mapped_column(String(16))
    # A direct post's privacy level, as TikTok names it (SELF_ONLY...); None for a draft and any other post.
    privacy_level: Mapped[str | None] = mapped_column(String(32))

    fanpage: Mapped[Fanpage | None] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    closed_by: Mapped[User | None] = relationship(foreign_keys=[closed_by_id])
    affiliate_account: Mapped["AffiliateAccount | None"] = relationship()
    metrics: Mapped[list["PostMetrics"]] = relationship(lazy="selectin", passive_deletes=True)


class PostMetrics(Base):
    """A post's numbers on Facebook: `latest`, rewritten by every reading, and `48h`, the first reading at least 48 hours
    after the post went live, kept as it is so posts are compared at the same age (docs/decisions.md). A number is None
    when Facebook does not give it."""

    __tablename__ = "post_metrics"
    __table_args__ = (Index("uq_post_metrics_publication_id_window", "publication_id", "window", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"))
    window: Mapped[str] = mapped_column(String(8))  # latest | 48h
    views: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    reactions: Mapped[int | None] = mapped_column(Integer)
    plays: Mapped[int | None] = mapped_column(BigInteger)  # plays without replays
    replays: Mapped[int | None] = mapped_column(BigInteger)
    reach: Mapped[int | None] = mapped_column(BigInteger)  # people who saw the reel, estimated by Facebook
    avg_watch_ms: Mapped[int | None] = mapped_column(BigInteger)  # per play, replays included
    view_time_ms: Mapped[int | None] = mapped_column(BigInteger)  # all plays together
    followers: Mapped[int | None] = mapped_column(BigInteger)  # follows the reel brought the Page
    # Share of plays still watching at each evenly spaced point of the reel, from 1.0 at the start.
    retention: Mapped[list | None] = mapped_column(JSONB)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PageComment(Base):
    """A visitor's comment under a reel the app posted, read by the worker (comments_inbox.py) for "Bình luận". A reply
    or a hide a member asks for is stamped before Facebook is asked, so it is never sent twice."""

    __tablename__ = "page_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"), index=True)
    remote_id: Mapped[str] = mapped_column(String(80), unique=True)  # Facebook's comment id
    author_name: Mapped[str] = mapped_column(String(200), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The Page already answered it on Facebook (found by the worker), or through the app (`reply_id`).
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # "Bỏ qua": no answer needed
    reply_text: Mapped[str | None] = mapped_column(Text)
    reply_id: Mapped[str | None] = mapped_column(String(80))
    reply_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hide_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hide_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    handled_by: Mapped[User | None] = relationship()
    publication: Mapped[Publication] = relationship()


ARTICLE_KINDS = ("kien_thuc", "meo", "cau_hoi", "canh_bao", "tra_loi_binh_luan", "checklist")
ARTICLE_IMAGE_KINDS = ("ai", "link", "text_card")


class Article(Base):
    """A photo or text post for a Page ("Bài viết", articles.py): a cheap test of a topic before a reel is made.
    Named "article" in code because "post" already means a `publications` row. Its posting status will come from its
    publications, as a video's does; until then it is a draft. Without a picture it is a text-only post."""

    __tablename__ = "articles"
    __table_args__ = (
        CheckConstraint(f"kind IN {ARTICLE_KINDS}", name="kind"),
        CheckConstraint(f"image_kind IS NULL OR image_kind IN {ARTICLE_IMAGE_KINDS}", name="image_kind"),
        Index("ix_articles_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_topic_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_topics.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(32))  # one of ARTICLE_KINDS
    topic: Mapped[str] = mapped_column(Text, default="", server_default="")  # what it is about ("Chủ đề")
    caption: Mapped[str] = mapped_column(Text, default="", server_default="")
    hashtags: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    image_key: Mapped[str | None] = mapped_column(String(200))
    image_kind: Mapped[str | None] = mapped_column(String(16))  # one of ARTICLE_IMAGE_KINDS
    image_source: Mapped[str | None] = mapped_column(Text)  # a pasted photo's link, kept for a copyright claim
    # The comment the worker writes under the post opens with this, then the products' links (as a video's).
    pinned_comment: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Product ideas to search Shopee for ("Tìm sản phẩm"), and that search, as on a video (affiliate_rounds.suggest).
    affiliates: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    suggest_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suggest_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    suggested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suggest_error: Mapped[str | None] = mapped_column(Text)
    # The visitor's comment a "tra_loi_binh_luan" article answers.
    source_comment_id: Mapped[int | None] = mapped_column(ForeignKey("page_comments.id", ondelete="SET NULL"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    source_comment: Mapped[PageComment | None] = relationship()


class MediaItem(Base):
    """A photo or clip in the team's "Kho tư liệu" (routes_media.py): uploaded, a whole folder at a time, or downloaded
    from a pasted link (a photo from Google Ảnh, a TikTok video). Using it in a scene copies the file, like "Đã dùng
    trong nhóm", so deleting it never changes a video."""

    __tablename__ = "media_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # photo | clip
    storage_key: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    # The folder it was dragged in with ("noi-chien-5L/canh-quay"), or one a member typed; "" for none.
    folder: Mapped[str] = mapped_column(String(200), default="", server_default="", index=True)
    source_url: Mapped[str | None] = mapped_column(Text)  # the link it came from, kept for a copyright claim
    seconds: Mapped[float | None] = mapped_column(Float)  # a clip's length
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped[User] = relationship()


class MusicTrack(Base):
    """A track in the team library. Choosing it for a video copies the file into the video's folder, so editing
    or deleting the track never changes a video."""

    __tablename__ = "music_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    topics: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # names of Kho kiến thức groups, or "chung" (music_topics.py)
    mood: Mapped[str] = mapped_column(String(40))  # a value from music.MOODS
    license_note: Mapped[str] = mapped_column(Text, default="")
    storage_key: Mapped[str] = mapped_column(String(200))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped[User] = relationship()


class AffiliateAccount(Base):
    """A member's own account on an affiliate platform: Shopee (with the Open API's App ID and Secret, which only ever
    go in) or TikTok (the TikTok account itself, whose cart is TikTok Shop's). Only its owner sees or changes it."""

    __tablename__ = "affiliate_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16))  # shopee | tiktok
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    app_id: Mapped[str | None] = mapped_column(String(64))
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    secret_tail: Mapped[str | None] = mapped_column(String(8))
    profile_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # The worker's last reading of the account's orders (affiliate_rounds.py), and what went wrong then.
    report_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_error: Mapped[str | None] = mapped_column(Text)


class TikTokConnection(Base):
    """A member's TikTok account connected through TikTok's Login Kit (tiktok_connections.py), on their TikTok
    AffiliateAccount. Both tokens are encrypted like a Fanpage token (crypto.py) and never leave the server; TikTok
    gives a new refresh token with every refresh, so both are saved over the old ones each time."""

    __tablename__ = "tiktok_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    affiliate_account_id: Mapped[int] = mapped_column(
        ForeignKey("affiliate_accounts.id", ondelete="CASCADE"), unique=True
    )
    open_id: Mapped[str] = mapped_column(String(100), unique=True)  # TikTok's id of the account, for this app
    username: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # What went wrong refreshing the tokens (TikTok revoked them...): the member has to connect again.
    last_error: Mapped[str | None] = mapped_column(Text)


class TikTokOAuthState(Base):
    """A "Kết nối TikTok" on its way through TikTok's authorize page: the hash of its `state`, the member who started
    it, and when it lapses. Used once."""

    __tablename__ = "tiktok_oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AffiliateProduct(Base):
    """A product the team may promote, on Shopee or TikTok Shop: typed in by a member or found through Shopee's API
    (`shopee_item_id`). Rows start as drafts; only a member's approval makes one usable, and changing an approved row
    undoes that."""

    __tablename__ = "affiliate_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_topic_id: Mapped[int] = mapped_column(ForeignKey("knowledge_topics.id"))
    name: Mapped[str] = mapped_column(String(300))
    platform: Mapped[str] = mapped_column(String(16), default="shopee", server_default="shopee")  # | tiktok_shop
    # The affiliate link a member pasted. Products found through the API have none: each Page gets its own link.
    url: Mapped[str | None] = mapped_column(Text)
    page_url: Mapped[str | None] = mapped_column(Text)  # the product's own page, from the API
    image_url: Mapped[str | None] = mapped_column(Text)
    shopee_item_id: Mapped[int | None] = mapped_column(BigInteger)
    commission_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offer_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the daily check, last done
    # A pasted link or an imported row waits for the worker to read the product from Shopee (affiliate_rounds.lookup).
    lookup_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lookup_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    lookup_error: Mapped[str | None] = mapped_column(Text)
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


class ArticleAffiliateProduct(Base):
    """A product whose link goes in the comment under a posted article; at most articles.MAX_PRODUCTS per article."""

    __tablename__ = "article_affiliate_products"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("affiliate_products.id", ondelete="CASCADE"), primary_key=True)


class AffiliateLink(Base):
    """A Shopee short link made with a Page's account for one video, or one article, on that Page, so an order names
    both."""

    __tablename__ = "affiliate_links"
    __table_args__ = (
        Index(
            "uq_affiliate_links_video",
            "product_id",
            "account_id",
            "video_id",
            "fanpage_id",
            unique=True,
            postgresql_where=text("video_id IS NOT NULL"),
        ),
        Index(
            "uq_affiliate_links_article",
            "product_id",
            "account_id",
            "article_id",
            "fanpage_id",
            unique=True,
            postgresql_where=text("article_id IS NOT NULL"),
        ),
        CheckConstraint("(video_id IS NULL) <> (article_id IS NULL)", name="one_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("affiliate_products.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("affiliate_accounts.id", ondelete="CASCADE"))
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    fanpage_id: Mapped[int] = mapped_column(ForeignKey("fanpages.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AffiliateSuggestion(Base):
    """A product Shopee's search gave for one of the product ideas of a video, or of an article, best first."""

    __tablename__ = "affiliate_suggestions"
    __table_args__ = (CheckConstraint("(video_id IS NULL) <> (article_id IS NULL)", name="one_target"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    keyword: Mapped[str] = mapped_column(String(200))
    product_id: Mapped[int] = mapped_column(ForeignKey("affiliate_products.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)

    product: Mapped[AffiliateProduct] = relationship()


class AffiliateConversion(Base):
    """One item of an order Shopee credits to a member's account, with the video and Page its link was made for."""

    __tablename__ = "affiliate_conversions"
    __table_args__ = (UniqueConstraint("account_id", "external_id", name="uq_affiliate_conversions_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("affiliate_accounts.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(100))  # Shopee's order and item
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"))
    fanpage_id: Mapped[int | None] = mapped_column(ForeignKey("fanpages.id", ondelete="SET NULL"))
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    item_name: Mapped[str] = mapped_column(String(300))
    commission: Mapped[int] = mapped_column(Integer)  # VND
    status: Mapped[str] = mapped_column(String(32))
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
