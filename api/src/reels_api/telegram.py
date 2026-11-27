"""Private Telegram messages to each member (docs/decisions/2026-11-26-telegram-private.md).

The team's one bot (`TELEGRAM_BOT_TOKEN`, the bot that posts "Có gì mới" to the shared group) tells each member, in
their own chat with it, only about their own work: their video waiting for review (the MP4 with Duyệt / Bỏ buttons),
their failed jobs, their Page / TikTok / YouTube connections that stopped working, and a morning reminder. Nothing
personal ever goes to the group.

- **Linking:** Cài đặt › Thông báo Telegram gives a one-time `t.me/<bot>?start=<code>` link; the bot's /start with that
  code links the chat to the member (`users.telegram_chat_id`). /stop or "Ngắt kết nối" unlinks it.
- **Telegram talks to us through a webhook** (`/api/telegram/webhook`, routes_telegram.py), set when a member links,
  checked with a secret derived from the token: buttons answer at once, even while the worker renders.
- **What to tell is found by reading the database** (`collect`), not by hooking every code path: a `review_requested`
  event, a failed job, a connection error, the morning's state. Each becomes a `telegram_notices` row whose key is
  unique per member, so nothing is told twice; the worker sends them (`deliver`) between jobs.
- Without a token nothing is collected or sent, and the settings page says the bot is off.
"""

import hashlib
import html
import json
import logging
import secrets
import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import aliased, sessionmaker

from . import config, media_cleanup, page_queue, plans, review
from .analytics import VIETNAM
from .errors import ApiError
from .models import (
    Article,
    Fanpage,
    Job,
    KnowledgeTopic,
    PageQueueItem,
    Publication,
    TelegramNotice,
    TikTokConnection,
    User,
    Video,
    VideoEvent,
    YouTubeConnection,
)
from .sessions import now
from .videos import ensure_unlocked, lock_video

log = logging.getLogger(__name__)

# What a member can be told; each can be muted on the settings page.
KINDS = {
    "review": "Video của tôi chờ duyệt (kèm MP4 và nút Duyệt / Bỏ)",
    "failed": "Việc của tôi bị lỗi (render, đăng bài, viết kịch bản...)",
    "connection": "Fanpage, TikTok, YouTube của tôi mất kết nối",
    "reminder": "Nhắc việc lúc 8 giờ sáng",
    "muse": "Tin Muse gửi cho tôi",
}
LINK_TTL = timedelta(minutes=30)
# Nothing older than this is told: a member who links today does not get last week's failures.
WINDOW = timedelta(hours=24)
MAX_TRIES = 3
REMINDER_HOUR = 8  # Vietnam time
ROUND_SECONDS = 15.0
# Telegram takes a video of up to 50 MB from a bot; a bigger MP4 goes as a link to the app.
VIDEO_LIMIT = 49 * 1024 * 1024
CAPTION_LIMIT = 1024
SIGNATURE_CHARS = 16
WEBHOOK_PATH = "/api/telegram/webhook"
OFF = "Bot Telegram chưa bật: người quản lý cần thêm TELEGRAM_BOT_TOKEN cho api và worker (docs/deployment.md)"
HELP = (
    "Đây là bot của Reels Studio. Bot nhắn riêng cho bạn khi video của bạn chờ duyệt, khi việc của bạn bị lỗi, "
    "khi kết nối hết hạn, và nhắc việc mỗi sáng.\n\n"
    "Để kết nối: vào Reels Studio › Cài đặt › Thông báo Telegram và bấm <b>Kết nối Telegram</b>.\n"
    "/help: các lệnh của bot. /stop: ngừng nhận tin."
)
JOB_LABELS = {
    "script": "Viết kịch bản",
    "clone": "Nhân bản video",
    "learn": "Học video mẫu",
    "render": "Render",
    "publish": "Đăng Facebook",
    "unpublish": "Gỡ bài Facebook",
    "check": "Kiểm tra bài Facebook",
    "image": "Tạo ảnh AI",
    "photos": "Tự tìm ảnh",
    "voice": "Tạo giọng đọc",
    "plan": "Tạo kế hoạch bằng AI",
    "revise": "Nhờ AI sửa",
    "article_caption": "Viết caption bài viết",
    "motion": "Cảnh động",
    "tiktok_publish": "Đăng TikTok",
    "youtube_publish": "Tải lên YouTube",
    "ig_publish": "Đăng Instagram",
    "image_edit": "Sửa ảnh",
    "slot_comments": "Tạo bình luận ghim",
    "text_look": "AI gợi ý chữ",
}


class TelegramError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def configured() -> bool:
    return bool(config.telegram_bot_token())


def call(method: str, data: dict | None = None, files: dict | None = None) -> dict | bool:
    """One Bot API call; raises TelegramError with Telegram's own words. The token is never put in a message."""
    url = f"{config.telegram_api_url()}/bot{config.telegram_bot_token()}/{method}"
    try:
        if files:
            fields = {k: v if isinstance(v, str) else json.dumps(v) for k, v in (data or {}).items()}
            response = httpx.post(url, data=fields, files=files, timeout=120)
        else:
            response = httpx.post(url, json=data or {}, timeout=20)
    except httpx.HTTPError as err:
        raise TelegramError(f"Không gọi được Telegram ({type(err).__name__})") from None
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not body.get("ok"):
        raise TelegramError(body.get("description") or f"Telegram trả lời {response.status_code}", response.status_code)
    return body.get("result")


_usernames: dict[str, str] = {}
_webhooks: set[tuple[str, str]] = set()


def bot_username() -> str:
    token = config.telegram_bot_token()
    if token not in _usernames:
        _usernames[token] = call("getMe")["username"]
    return _usernames[token]


def webhook_secret() -> str:
    """Telegram sends it back in a header with every update: only Telegram, which got it from us, knows it."""
    return hashlib.sha256(f"reels-telegram-webhook:{config.telegram_bot_token()}".encode()).hexdigest()


def ensure_webhook() -> None:
    """Once per process: Telegram sends the bot's updates to the api. Setting it again is harmless."""
    url = config.web_url() + WEBHOOK_PATH
    if (config.telegram_bot_token(), url) in _webhooks:
        return
    call(
        "setWebhook",
        {"url": url, "secret_token": webhook_secret(), "allowed_updates": ["message", "callback_query"]},
    )
    from .telegram_commands import COMMANDS

    # The "/" menu, in private chats and in groups (where Telegram adds @<bot> to what is picked).
    call("setMyCommands", {"commands": [{"command": name, "description": text} for name, text in COMMANDS]})
    _webhooks.add((config.telegram_bot_token(), url))


def app_link(path: str) -> str:
    return config.web_url() + path


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def send_text(chat_id: int, text: str, buttons: list | None = None) -> dict:
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    return call("sendMessage", data)


# --- Linking (the settings page and the bot's /start) ---


def status(user: User) -> dict:
    return {
        "configured": configured(),
        "linked": user.telegram_chat_id is not None,
        "username": user.telegram_username,
        "linked_at": user.telegram_linked_at.isoformat() if user.telegram_linked_at else None,
        "muted": [kind for kind in user.telegram_muted or [] if kind in KINDS],
        "kinds": [{"key": key, "label": label} for key, label in KINDS.items()],
    }


def start_link(user: User) -> str:
    """The one-time link that opens the bot; its /start links this member's chat. Caller commits."""
    if not configured():
        raise ApiError(409, "telegram_off", OFF)
    try:
        name = bot_username()
        ensure_webhook()
    except TelegramError as err:
        raise ApiError(502, "telegram_unreachable", f"Không kết nối được Telegram: {err}") from None
    code = secrets.token_urlsafe(24)
    user.telegram_link_code_hash, user.telegram_link_expires_at = _hash(code), now() + LINK_TTL
    return f"https://t.me/{name}?start={code}"


def unlink(user: User, tell: bool = True) -> None:
    chat = user.telegram_chat_id
    user.telegram_chat_id = user.telegram_username = user.telegram_linked_at = None
    if chat and tell and configured():
        try:
            send_text(chat, "Đã ngắt kết nối với Reels Studio. Bot sẽ không nhắn cho bạn nữa.")
        except TelegramError:
            pass


def _link(db: DbSession, chat_id: int, sender: dict, code: str) -> None:
    user = None
    if code:
        user = db.scalar(
            select(User).where(
                User.telegram_link_code_hash == _hash(code),
                User.telegram_link_expires_at > now(),
                User.is_active.is_(True),
            )
        )
    if user is None:
        send_text(
            chat_id,
            "Link kết nối đã hết hạn hoặc không đúng.\n\n" + HELP if code else HELP,
        )
        return
    for other in db.scalars(select(User).where(User.telegram_chat_id == chat_id, User.id != user.id)):
        other.telegram_chat_id = other.telegram_username = other.telegram_linked_at = None
    db.flush()
    user.telegram_chat_id = chat_id
    user.telegram_username = (sender.get("username") or sender.get("first_name") or "")[:64] or None
    user.telegram_linked_at = now()
    user.telegram_link_code_hash = user.telegram_link_expires_at = None
    db.commit()
    send_text(
        chat_id,
        f"✅ Đã kết nối với tài khoản <b>{html.escape(user.name)}</b> của Reels Studio.\n\n"
        "Từ giờ bot nhắn riêng cho bạn: video của bạn chờ duyệt (bấm Duyệt ngay tại đây), việc bị lỗi, kết nối hết hạn "
        "và nhắc việc lúc 8 giờ sáng. Tin trong nhóm chung vẫn chỉ là tin chung của cả đội.\n"
        "Chọn loại tin trong Cài đặt › Thông báo Telegram. /stop: ngừng nhận tin.",
    )


# --- Updates from Telegram (the webhook) ---


def handle_update(db: DbSession, update: dict) -> None:
    """Never raises for a bad update: Telegram would send it again and again."""
    try:
        if update.get("callback_query"):
            _button(db, update["callback_query"])
        elif update.get("message"):
            _message(db, update["message"])
    except TelegramError as err:
        db.rollback()
        log.warning("Telegram answer failed: %s", err)


def _message(db: DbSession, message: dict) -> None:
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    command, _, rest = text.partition(" ")
    command = command.split("@")[0].lower()
    if command == "/chatid":
        # For setting up the team's group (docs/deployment.md): the id the CI posts "Có gì mới" to.
        send_text(chat["id"], f"Chat id: <code>{chat['id']}</code>")
        return
    from . import telegram_commands

    if telegram_commands.handle(db, message, command, rest.strip()):
        return
    if chat.get("type") != "private":
        return  # in a group the bot answers its commands only, never anything personal
    if command == "/start":
        _link(db, chat["id"], message.get("from") or {}, rest.strip())
    elif command == "/stop":
        user = db.scalar(select(User).where(User.telegram_chat_id == chat["id"]))
        if user is None:
            send_text(chat["id"], "Telegram này chưa kết nối với Reels Studio.")
            return
        unlink(user)
        db.commit()
    else:
        send_text(chat["id"], HELP)


def _buttons(video: Video, can_approve: bool, approve_action: str = "ap") -> list:
    rows = []
    signature = (video.rendered_signature or "")[:SIGNATURE_CHARS]
    if can_approve:
        rows.append(
            [
                {
                    "text": "✅ Duyệt" if approve_action == "ap" else "✅ Vẫn duyệt",
                    "callback_data": f"{approve_action}:{video.id}:{signature}",
                },
                {"text": "❌ Bỏ video", "callback_data": f"rj:{video.id}:{signature}"},
            ]
        )
    if config.web_url().startswith("https://"):
        rows.append([{"text": "Mở trong app", "url": app_link(f"/videos/{video.id}")}])
    return rows


def _video_name(video: Video) -> str:
    return video.name or video.topic or f"Video #{video.id}"


def _button(db: DbSession, query: dict) -> None:
    sender = (query.get("from") or {}).get("id")
    chat = ((query.get("message") or {}).get("chat") or {}).get("id")
    message_id = (query.get("message") or {}).get("message_id")

    def answer(text: str, alert: bool = False) -> None:
        call("answerCallbackQuery", {"callback_query_id": query["id"], "text": text[:200], "show_alert": alert})

    user = db.scalar(select(User).where(User.telegram_chat_id == sender, User.is_active.is_(True)))
    if user is None or sender is None:
        answer("Telegram này chưa kết nối với Reels Studio", True)
        return
    action, _, rest = (query.get("data") or "").partition(":")
    video_id, _, signature = rest.partition(":")
    if action in ("qa", "qp", "rv"):
        from . import telegram_commands

        answer(telegram_commands.button(db, user, action, rest, chat))
        return
    if action not in ("ap", "aq", "rj") or not video_id.isdigit():
        answer("Nút này không còn dùng được")
        return
    try:
        video = lock_video(db, int(video_id))
        if (video.rendered_signature or "")[:SIGNATURE_CHARS] != signature:
            raise ApiError(409, "stale", "Video đã có bản render mới, hãy xem tin mới nhất")
        if action == "rj":
            ensure_unlocked(db, video)
            review.reject(db, video, user.id, "telegram", "Bỏ từ Telegram")
            done = "❌ Đã bỏ video"
        else:
            review.approve(db, video, user.id, "telegram", acknowledge_qc=action == "aq")
            done = "✅ Đã duyệt"
        db.commit()
    except ApiError as err:
        db.rollback()
        if err.code == "qc_not_acknowledged":
            video = db.get(Video, int(video_id))
            items = review.qc_report(db, video)["items"]
            lines = "\n".join(f"• {html.escape(item['message'][:150])}" for item in items[:5])
            send_text(
                chat,
                f"⚠️ <b>{html.escape(_video_name(video))}</b> còn {len(items)} mục cần xem:\n{lines}\n\n"
                "Đã xem và vẫn muốn duyệt thì bấm <b>Vẫn duyệt</b>.",
                _buttons(video, True, "aq"),
            )
            answer("Còn mục cần xem trước khi duyệt")
            return
        answer(err.message, True)
        return
    answer(done)
    if chat and message_id:
        try:
            call(
                "editMessageReplyMarkup",
                {
                    "chat_id": chat,
                    "message_id": message_id,
                    "reply_markup": {"inline_keyboard": _buttons(video, False)},
                },
            )
        except TelegramError:
            pass  # the message may be too old to edit; the answer below says what happened
    from . import telegram_commands

    if action == "rj":
        telegram_commands.ask_reason(chat, video)
    else:
        telegram_commands.offer_queue(db, user, chat, video, done)


# --- What to tell (collect) ---


def _linked(db: DbSession) -> dict[int, User]:
    return {
        user.id: user
        for user in db.scalars(select(User).where(User.telegram_chat_id.is_not(None), User.is_active.is_(True)))
    }


def _add(
    db: DbSession, user: User, key: str, kind: str, text: str, link: str | None, video_id: int | None = None
) -> bool:
    if kind in (user.telegram_muted or []):
        return False
    if db.scalar(select(exists().where(TelegramNotice.user_id == user.id, TelegramNotice.key == key))):
        return False
    db.add(TelegramNotice(user_id=user.id, key=key, kind=kind, text=text, link=link, video_id=video_id))
    db.flush()
    return True


def collect(db: DbSession, at: datetime | None = None) -> int:
    """Writes a notice for each new thing a linked member should hear about; returns how many. Caller commits."""
    at = at or now()
    users = _linked(db)
    if not users:
        return 0
    added = _reviews(db, users, at) + _failures(db, users, at) + _connections(db, users)
    added += _reminders(db, users, at)
    return added


def _reviews(db: DbSession, users: dict[int, User], at: datetime) -> int:
    rows = db.execute(
        select(VideoEvent, Video)
        .join(Video, Video.id == VideoEvent.video_id)
        .where(
            VideoEvent.type == "review_requested",
            VideoEvent.created_at >= at - WINDOW,
            Video.created_by_id.in_(users),
            Video.review_status == review.PENDING,
            Video.mp4_key.is_not(None),
        )
        .order_by(VideoEvent.id)
    ).all()
    added = 0
    for event, video in rows:
        user = users[video.created_by_id]
        if event.created_at < user.telegram_linked_at:
            continue
        text = f"🎬 <b>Video chờ bạn duyệt</b>\n{html.escape(_video_name(video))}"
        added += _add(db, user, f"review:{event.id}", "review", text, f"/videos/{video.id}", video.id)
    return added


def _failures(db: DbSession, users: dict[int, User], at: datetime) -> int:
    # A job already tried again ("Thử lại", or the worker's own retry after a restart) is not news any more.
    again = aliased(Job)
    retried = select(again.retry_of_id).where(again.retry_of_id.is_not(None))
    jobs = db.scalars(
        select(Job)
        .where(
            Job.status == "failed",
            Job.finished_at >= at - WINDOW,
            Job.created_by_id.in_(users),
            Job.id.not_in(retried),
        )
        .order_by(Job.id)
    ).all()
    added = 0
    for job in jobs:
        user = users[job.created_by_id]
        if job.finished_at < user.telegram_linked_at:
            continue
        if job.article_id is not None and _article_will_retry(db, job.article_id):
            continue  # article_posts tries again by itself; the member hears only if that fails for good
        subject, link = _subject(db, job)
        label = JOB_LABELS.get(job.kind, f"Việc {job.kind}")
        text = f"⚠️ <b>{label} không thành công</b>\n{html.escape(subject)}"
        if job.error:
            text += f"\nLý do: {html.escape(job.error[:300])}"
        added += _add(db, user, f"job:{job.id}", "failed", text, link)
    return added


def _article_will_retry(db: DbSession, article_id: int) -> bool:
    return bool(
        db.scalar(select(exists().where(Publication.article_id == article_id, Publication.retry_at.is_not(None))))
    )


def _subject(db: DbSession, job: Job) -> tuple[str, str]:
    if job.video_id is not None and (video := db.get(Video, job.video_id)) is not None:
        return _video_name(video), f"/videos/{video.id}"
    if job.article_id is not None and (article := db.get(Article, job.article_id)) is not None:
        return f"Bài viết: {article.topic or article.caption[:60] or f'#{article.id}'}", "/articles"
    if job.knowledge_topic_id is not None and (topic := db.get(KnowledgeTopic, job.knowledge_topic_id)) is not None:
        return f"Nhóm chủ đề: {topic.name}", "/knowledge"
    return f"Việc #{job.id}", "/jobs"


def _connections(db: DbSession, users: dict[int, User]) -> int:
    broken: list[tuple[int | None, str, str, str]] = []  # (member, key, text, link)
    for page in db.scalars(select(Fanpage).where(Fanpage.active.is_(True), Fanpage.check_error.is_not(None))):
        broken.append(
            (
                page.owner_id or page.updated_by_id,
                f"conn:fanpage:{page.id}",
                f"🔌 <b>Fanpage {html.escape(page.name)} mất kết nối</b>\n{html.escape(page.check_error[:300])}\n"
                "Vào trang Fanpage để kết nối lại, không thì bài hẹn giờ của Page này có thể không đăng được.",
                "/fanpages",
            )
        )
    for account in db.scalars(select(TikTokConnection).where(TikTokConnection.last_error.is_not(None))):
        broken.append(
            (
                account.owner_id,
                f"conn:tiktok:{account.id}",
                f"🔌 <b>TikTok @{html.escape(account.username)} mất kết nối</b>\n"
                f"{html.escape(account.last_error[:300])}\nVào Cài đặt › Tài khoản và kênh để kết nối lại.",
                "/settings/affiliate-accounts",
            )
        )
    for channel in db.scalars(select(YouTubeConnection).where(YouTubeConnection.last_error.is_not(None))):
        broken.append(
            (
                channel.owner_id,
                f"conn:youtube:{channel.id}",
                f"🔌 <b>YouTube {html.escape(channel.title)} mất kết nối</b>\n"
                f"{html.escape(channel.last_error[:300])}\nVào Cài đặt › Tài khoản và kênh để kết nối lại.",
                "/settings/affiliate-accounts",
            )
        )
    # A connection that works again forgets it was told, so the next time it breaks is told again.
    keys = [key for _, key, _, _ in broken]
    db.execute(
        delete(TelegramNotice).where(
            TelegramNotice.kind == "connection", TelegramNotice.sent_at.is_not(None), TelegramNotice.key.not_in(keys)
        )
    )
    added = 0
    for owner, key, text, link in broken:
        if owner in users:
            added += _add(db, users[owner], key, "connection", text, link)
    return added


def _reminders(db: DbSession, users: dict[int, User], at: datetime) -> int:
    local = at.astimezone(VIETNAM)
    if local.hour < REMINDER_HOUR:
        return 0
    added = 0
    key = f"daily:{local.date().isoformat()}"
    for user in users.values():
        if "reminder" in (user.telegram_muted or []) or db.scalar(
            select(exists().where(TelegramNotice.user_id == user.id, TelegramNotice.key == key))
        ):
            continue
        lines = reminder_lines(db, user, at)
        if lines:
            text = "☀️ <b>Nhắc việc hôm nay</b>\n" + "\n".join(f"• {line}" for line in lines)
            added += _add(db, user, key, "reminder", text, "/videos")
        else:
            # Nothing to remind: remembered as told, so the day is not looked at again.
            db.add(TelegramNotice(user_id=user.id, key=key, kind="reminder", text="", sent_at=at, error="Không có gì"))
            db.flush()
    return added


def reminder_lines(db: DbSession, user: User, at: datetime) -> list[str]:
    lines = []
    waiting = db.scalar(
        select(func.count())
        .select_from(Video)
        .where(Video.created_by_id == user.id, Video.review_status == review.PENDING, Video.mp4_key.is_not(None))
    )
    if waiting:
        lines.append(f"{waiting} video của bạn đang chờ duyệt")
    due_ids = {due.video_id for due in media_cleanup.soon(db, at)}
    cleaning = (
        db.scalars(select(Video.id).where(Video.created_by_id == user.id, Video.id.in_(due_ids))).all()
        if due_ids
        else []
    )
    if cleaning:
        lines.append(
            f"{len(cleaning)} video của bạn sắp bị dọn media trong 3 ngày tới (ảnh, clip, lời đọc; MP4 vẫn giữ). "
            "Muốn giữ thì mở video, tab Thiết lập, bật “Giữ media”"
        )
    pages = db.scalars(
        select(Fanpage)
        .where(Fanpage.owner_id == user.id, Fanpage.active.is_(True), Fanpage.check_error.is_(None))
        .order_by(Fanpage.name)
    ).all()
    for page in pages:
        times = page_queue.post_times(db, page)
        if not times:
            continue
        ready = db.scalar(
            select(func.count()).select_from(PageQueueItem).where(PageQueueItem.fanpage_id == page.id)
        ) + db.scalar(
            select(func.count())
            .select_from(Publication)
            .where(Publication.fanpage_id == page.id, Publication.status == "scheduled", Publication.scheduled_at > at)
        )
        if ready < len(times):
            lines.append(
                f"Page {html.escape(page.name)} chỉ còn {ready} video hẹn giờ hoặc trong hàng chờ "
                f"(mỗi ngày đăng {len(times)} lần)"
            )
    today = at.astimezone(VIETNAM).date()
    for topic in db.scalars(
        select(KnowledgeTopic)
        .where(KnowledgeTopic.id.in_({page.knowledge_topic_id for page in pages if page.knowledge_topic_id}))
        .where(KnowledgeTopic.plan_start_date.is_not(None))
        .order_by(KnowledgeTopic.name)
    ):
        day = plans.day_of(topic.plan_start_date, today)
        if not 1 <= day <= plans.PLAN_DAYS:
            continue
        missing = [item for item in plans.items_of(db, topic.id) if item.day == day and item.video_id is None]
        if missing:
            lines.append(
                f"Kế hoạch {html.escape(topic.name)}, ngày {day}/{plans.PLAN_DAYS}: "
                f"còn {len(missing)} ý tưởng hôm nay chưa có video"
            )
    return lines


def tell(user: User, text: str, link: str | None = None) -> None:
    """A message to one member from Muse (MCP "Nhắn riêng qua Telegram"), sent at once to that member's own chat.
    Raises ApiError when it cannot go: the bot is off, the member has not linked Telegram or muted Muse's messages."""
    if not configured():
        raise ApiError(409, "telegram_off", OFF)
    if user.telegram_chat_id is None:
        raise ApiError(
            409,
            "telegram_not_linked",
            "Thành viên chưa kết nối Telegram (Cài đặt › Thông báo Telegram); hãy báo trong chat thay vào đó",
        )
    if "muse" in (user.telegram_muted or []):
        raise ApiError(409, "telegram_muted", "Thành viên đã tắt tin Muse gửi qua Telegram; hãy báo trong chat")
    body = f"💬 <b>Muse</b>\n{html.escape(text)}"
    if link:
        body += f'\n\n<a href="{html.escape(link)}">Mở</a>'
    try:
        send_text(user.telegram_chat_id, body)
    except TelegramError as err:
        raise ApiError(502, "telegram_unreachable", f"Telegram chưa nhận tin: {err}") from None


# --- Sending (deliver) ---


def deliver(db: DbSession, storage, at: datetime | None = None, limit: int = 20) -> int:
    """Sends the notices not sent yet; returns how many went. A failure is kept and tried again, up to MAX_TRIES."""
    at = at or now()
    rows = db.scalars(
        select(TelegramNotice)
        .where(
            TelegramNotice.sent_at.is_(None),
            TelegramNotice.tries < MAX_TRIES,
            TelegramNotice.created_at >= at - WINDOW,
        )
        .order_by(TelegramNotice.id)
        .limit(limit)
    ).all()
    sent = 0
    for notice in rows:
        user = db.get(User, notice.user_id)
        try:
            if user.telegram_chat_id is None or notice.kind in (user.telegram_muted or []):
                notice.error = "Không gửi: thành viên đã ngắt kết nối hoặc tắt loại tin này"
            else:
                notice.error = _send(db, storage, user, notice)
                sent += notice.error is None
            notice.sent_at = now()
        except TelegramError as err:
            notice.tries += 1
            notice.error = str(err)[:500]
            if err.status == 403:  # they blocked the bot or deleted the chat: stop until they link again
                unlink(user, tell=False)
                notice.sent_at = now()
            log.warning("Telegram notice %s not sent: %s", notice.id, err)
        db.commit()
    return sent


def _send(db: DbSession, storage, user: User, notice: TelegramNotice) -> str | None:
    """Sends one notice; returns why it was left out (None when it went)."""
    if notice.kind != "review":
        text = notice.text
        if notice.link:
            text += f'\n\n<a href="{html.escape(app_link(notice.link))}">Mở trong Reels Studio</a>'
        send_text(user.telegram_chat_id, text)
        return None
    video = db.get(Video, notice.video_id) if notice.video_id else None
    if video is None or video.review_status != review.PENDING or not video.mp4_key:
        return "Không gửi: video đã được duyệt, bị bỏ hoặc xóa"
    send_review(db, storage, user.telegram_chat_id, video, notice.text)
    return None


def send_review(db: DbSession, storage, chat_id: int, video: Video, heading: str | None = None) -> None:
    """A video waiting for review: its MP4 (or a link when too big), its QC summary and the Duyệt / Bỏ buttons."""
    heading = heading or f"🎬 <b>Video chờ bạn duyệt</b>\n{html.escape(_video_name(video))}"
    items = review.qc_report(db, video)["items"]
    blockers = [item for item in items if item["level"] == "blocker"]
    lines = [heading]
    if blockers:
        lines.append(f"⛔ Chưa duyệt được: {html.escape(blockers[0]['message'][:200])}")
    elif items:
        lines.append(f"⚠️ {len(items)} mục cần xem trước khi duyệt:")
        lines += [f"• {html.escape(item['message'][:150])}" for item in items[:3]]
    if not config.web_url().startswith("https://"):
        lines.append(html.escape(app_link(f"/videos/{video.id}")))
    caption = "\n".join(lines)
    while len(caption) > CAPTION_LIMIT and len(lines) > 1:
        lines.pop()
        caption = "\n".join(lines)
    buttons = _buttons(video, not blockers)
    path = storage.path(video.mp4_key) if video.mp4_key else None
    if path is not None and path.is_file() and path.stat().st_size <= VIDEO_LIMIT:
        with open(path, "rb") as file:
            call(
                "sendVideo",
                {
                    "chat_id": str(chat_id),
                    "caption": caption,
                    "parse_mode": "HTML",
                    "supports_streaming": "true",
                    "reply_markup": {"inline_keyboard": buttons},
                },
                files={"video": (f"video-{video.id}.mp4", file, "video/mp4")},
            )
    else:
        send_text(chat_id, caption + "\n(MP4 quá lớn để gửi qua Telegram, xem trong app)", buttons)


_next_round = 0.0


def run_round(factory: sessionmaker) -> None:
    """The worker, between jobs: find what to tell and send it. Never raises; a problem waits for the next round."""
    global _next_round
    if not configured() or time.monotonic() < _next_round:
        return
    _next_round = time.monotonic() + ROUND_SECONDS
    try:
        from .storage import get_storage

        with factory() as db:
            collect(db)
            db.commit()
            deliver(db, get_storage())
            from . import telegram_commands

            telegram_commands.group_summary(db)
    except Exception:
        log.exception("Telegram round failed")
