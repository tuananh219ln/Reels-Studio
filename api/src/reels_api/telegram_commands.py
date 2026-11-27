"""The Telegram bot's commands, in the team's group and in each member's private chat
(docs/decisions/2026-11-26-telegram-commands.md). None of them calls an AI: they read the database and the app's guides.

The same commands work in both places. One about a member's own work (/cho_duyet, /hom_nay, /loi) asked in a group is
answered in that member's private chat, with only "Đã gửi riêng" in the group: nothing personal is ever said there.
Team-wide ones (/tong_quan, /moi, /huongdan, /help) are answered where they were asked. In a group the member is known
by their Telegram account, linked on Cài đặt › Thông báo Telegram (a private chat's id is the account's id).

Also here: after "Duyệt", a button per Page of the video's group to add it to that Page's queue; after "Bỏ", the bot
asks why and keeps the answer on the rejection; and the daily summary in the group.
"""

import html
import logging
import re
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import aliased

from . import changelog, config, page_queue, plans, review, routes_guides, telegram
from .analytics import VIETNAM
from .errors import ApiError
from .models import (
    AppSetting,
    Fanpage,
    Job,
    KnowledgeTopic,
    PostMetrics,
    Publication,
    User,
    Video,
    VideoEvent,
)
from .sessions import now

log = logging.getLogger(__name__)

# The "/" menu (setMyCommands): name and what it does, in the order shown.
COMMANDS = [
    ("cho_duyet", "Video của tôi đang chờ duyệt (gửi riêng)"),
    ("hom_nay", "Việc hôm nay của tôi (gửi riêng)"),
    ("loi", "Việc của tôi bị lỗi trong 24 giờ (gửi riêng)"),
    ("tong_quan", "Số liệu hôm nay của cả nhóm"),
    ("moi", "Có gì mới trong app"),
    ("huongdan", "Tìm hướng dẫn: /huongdan từ khoá"),
    ("help", "Các lệnh của bot"),
]
PERSONAL = {"/cho_duyet", "/hom_nay", "/loi"}
SUMMARY_HOUR = 21  # Vietnam time: the group's daily summary
SUMMARY_KEY = "telegram_group_summary"  # app_settings: the last day summed up
REASON_MARK = re.compile(r"\(#v(\d+)\)")
NOT_LINKED = (
    "Bạn chưa kết nối Telegram với Reels Studio. Vào Cài đặt › Thông báo Telegram và bấm "
    "<b>Kết nối Telegram</b>, rồi gõ lại lệnh."
)


def help_text() -> str:
    lines = [f"/{name}: {text}" for name, text in COMMANDS]
    return (
        "<b>Lệnh của bot Reels Studio</b>\n"
        + "\n".join(html.escape(line) for line in lines)
        + "\n\nTrong nhóm, gõ lệnh kèm tên bot (chọn từ menu “/” là tự có). Việc riêng của bạn luôn được gửi vào chat "
        "riêng với bot, không bao giờ hiện trong nhóm."
    )


def handle(db: DbSession, message: dict, command: str, rest: str) -> bool:
    """Answers a command, or a reply to "why was it rejected"; False when the message is not one of them."""
    chat = message.get("chat") or {}
    private = chat.get("type") == "private"
    sender = (message.get("from") or {}).get("id")
    if private and not command.startswith("/") and _reason_reply(db, message, sender):
        return True
    if command in ("/help",) or (command == "/start" and not private):
        telegram.send_text(chat["id"], help_text())
        return True
    if command == "/tong_quan":
        telegram.send_text(chat["id"], overview(db))
        return True
    if command == "/moi":
        telegram.send_text(chat["id"], whats_new())
        return True
    if command == "/huongdan":
        telegram.send_text(chat["id"], guides(rest))
        return True
    if command not in PERSONAL:
        return False
    user = db.scalar(select(User).where(User.telegram_chat_id == sender, User.is_active.is_(True)))
    if user is None:
        telegram.send_text(chat["id"], NOT_LINKED)
        return True
    if command == "/cho_duyet":
        text, buttons = pending(db, user)
    elif command == "/hom_nay":
        text, buttons = today(db, user), None
    else:
        text, buttons = failures(db, user), None
    telegram.send_text(user.telegram_chat_id, text, buttons)
    if not private:
        telegram.send_text(chat["id"], f"📩 Đã gửi riêng cho {html.escape(user.name)}.")
    return True


# --- Personal answers (always sent to the member's private chat) ---


def pending(db: DbSession, user: User) -> tuple[str, list | None]:
    videos = db.scalars(
        select(Video)
        .where(Video.created_by_id == user.id, Video.review_status == review.PENDING, Video.mp4_key.is_not(None))
        .order_by(Video.id.desc())
        .limit(10)
    ).all()
    if not videos:
        return "✅ Không có video nào của bạn đang chờ duyệt.", None
    text = f"🎬 <b>{len(videos)} video của bạn đang chờ duyệt</b>\nBấm một video để xem MP4 và duyệt."
    buttons = [[{"text": _name(video)[:60], "callback_data": f"rv:{video.id}"}] for video in videos]
    return text, buttons


def today(db: DbSession, user: User, at: datetime | None = None) -> str:
    at = at or now()
    local = at.astimezone(VIETNAM)
    start = datetime(local.year, local.month, local.day, tzinfo=VIETNAM)
    page = aliased(Fanpage)
    posts = db.execute(
        select(Publication, Video, page)
        .join(Video, Video.id == Publication.video_id)
        .outerjoin(page, page.id == Publication.fanpage_id)
        .where(
            Publication.status == "scheduled",
            Publication.scheduled_at >= start,
            Publication.scheduled_at < start + timedelta(days=1),
            (Video.created_by_id == user.id) | (page.owner_id == user.id),
        )
        .order_by(Publication.scheduled_at)
        .limit(15)
    ).all()
    lines = [f"📅 <b>Hôm nay {local:%d/%m} của bạn</b>"]
    if posts:
        lines.append("Bài hẹn đăng:")
        for post, video, fanpage in posts:
            where = fanpage.name if fanpage else post.platform
            lines.append(
                f"• {post.scheduled_at.astimezone(VIETNAM):%H:%M} · {html.escape(where)} · {html.escape(_name(video))}"
            )
    else:
        lines.append("Không có bài nào hẹn đăng hôm nay.")
    extra = telegram.reminder_lines(db, user, at)
    if extra:
        lines.append("Cần làm:")
        lines += [f"• {line}" for line in extra]
    return "\n".join(lines)


def failures(db: DbSession, user: User, at: datetime | None = None) -> str:
    at = at or now()
    again = aliased(Job)
    jobs = db.scalars(
        select(Job)
        .where(
            Job.status == "failed",
            Job.created_by_id == user.id,
            Job.finished_at >= at - timedelta(hours=24),
            Job.id.not_in(select(again.retry_of_id).where(again.retry_of_id.is_not(None))),
        )
        .order_by(Job.id.desc())
        .limit(10)
    ).all()
    if not jobs:
        return "✅ Không có việc nào của bạn bị lỗi trong 24 giờ qua."
    lines = [f"⚠️ <b>{len(jobs)} việc của bạn bị lỗi trong 24 giờ qua</b>"]
    for job in jobs:
        subject, link = telegram._subject(db, job)
        label = telegram.JOB_LABELS.get(job.kind, f"Việc {job.kind}")
        reason = f": {html.escape(job.error[:120])}" if job.error else ""
        lines.append(f'• <a href="{html.escape(telegram.app_link(link))}">{label}</a> · {html.escape(subject)}{reason}')
    lines.append("Mở từng việc trong app để xem chi tiết và bấm Thử lại.")
    return "\n".join(lines)


# --- Team-wide answers (said where they were asked) ---


def _day_bounds(at: datetime) -> tuple[datetime, datetime]:
    local = at.astimezone(VIETNAM)
    start = datetime(local.year, local.month, local.day, tzinfo=VIETNAM)
    return start, start + timedelta(days=1)


def overview(db: DbSession, at: datetime | None = None) -> str:
    """Numbers only: nobody's name, nobody's own work."""
    at = at or now()
    start, end = _day_bounds(at)

    def count(*where) -> int:
        return db.scalar(select(func.count()).select_from(Publication).where(Publication.video_id.is_not(None), *where))

    posted = count(Publication.status == "published", Publication.published_at >= start, Publication.published_at < end)
    later = count(Publication.status == "scheduled", Publication.scheduled_at >= at, Publication.scheduled_at < end)
    tomorrow = count(
        Publication.status == "scheduled",
        Publication.scheduled_at >= end,
        Publication.scheduled_at < end + timedelta(days=1),
    )
    return (
        f"📊 <b>Cả nhóm hôm nay {start:%d/%m}</b>\n"
        f"• Đã đăng: {posted} video\n"
        f"• Còn hẹn trong hôm nay: {later}\n"
        f"• Đã hẹn cho ngày mai: {tomorrow}\n"
        f"• Đang chờ duyệt: {review.pending_count(db)} video"
    )


def whats_new() -> str:
    try:
        changes = changelog.read(limit=5)["changes"]
    except ApiError as err:
        return html.escape(err.message)
    if not changes:
        return "Chưa có thay đổi nào."
    lines = ["🆕 <b>Có gì mới trong Reels Studio</b>"]
    for change in changes:
        lines.append(f"• <b>{html.escape(change['title'])}</b> ({html.escape(change['kind'] or '')})")
        if change.get("summary"):
            lines.append(f"  {html.escape(change['summary'][:200])}")
    lines.append(f'<a href="{html.escape(telegram.app_link("/whats-new"))}">Xem tất cả trong app</a>')
    return "\n".join(lines)


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[#*_`>\[\]()]", " ", text)).strip()


def guides(query: str) -> str:
    """The in-app guides whose title or text holds every word asked (all of them without words), with a link each and
    the lines that match."""
    found = routes_guides._read().values()
    words = [word for word in query.lower().split() if word]
    if words:
        found = [guide for guide in found if all(word in (guide["title"] + guide["body"]).lower() for word in words)]
    if not found:
        return f"Không tìm thấy hướng dẫn nào có “{html.escape(query)}”. Gõ /huongdan để xem tất cả, hoặc thử từ khoá khác."
    lines = ["📘 <b>Hướng dẫn</b>" + (f" có “{html.escape(query)}”" if words else "")]
    for guide in list(found)[:8]:
        link = telegram.app_link(f"/guides?guide={guide['slug']}")
        lines.append(f'• <a href="{html.escape(link)}">{html.escape(guide["title"])}</a>')
        if words:
            hits = [
                line
                for line in guide["body"].splitlines()
                if line.strip() and any(word in line.lower() for word in words)
            ]
            for hit in hits[:2]:
                lines.append(f"  › {html.escape(_plain(hit)[:180])}")
    return "\n".join(lines)


# --- Buttons and replies after Duyệt / Bỏ ---


def _name(video: Video) -> str:
    return video.name or video.topic or f"Video #{video.id}"


def queue_pages(db: DbSession, user: User, video: Video) -> list[Fanpage]:
    """The member's Pages that post the video's group: where "Thêm vào hàng chờ" can put it."""
    if video.knowledge_topic_id is None:
        return []
    return list(
        db.scalars(
            select(Fanpage)
            .where(
                Fanpage.active.is_(True),
                Fanpage.owner_id == user.id,
                Fanpage.knowledge_topic_id == video.knowledge_topic_id,
            )
            .order_by(Fanpage.name)
        )
    )


def _when(moment: datetime) -> str:
    local = moment.astimezone(VIETNAM)
    return f"{local:%H:%M %d/%m}"


def plan_time(db: DbSession, video: Video) -> datetime | None:
    """The video's plan idea's posting time, when it has one still to come."""
    idea = plans.idea_of_video(db, video.id)
    topic = db.get(KnowledgeTopic, idea.knowledge_topic_id) if idea else None
    return plans.suggested_post_at(topic, idea) if idea and topic else None


def offer_queue(db: DbSession, user: User, chat: int, video: Video, done: str) -> None:
    """After Duyệt: when to post, with the time shown before the press. The plan's time (if the video has one), or the
    Page's queue at the time it would give now; anything else is chosen in the app."""
    pages = queue_pages(db, user, video)
    text = f"{done}: <b>{html.escape(_name(video))}</b>."
    if not pages:
        telegram.send_text(chat, text + " Vào app để hẹn giờ đăng.")
        return
    planned = plan_time(db, video)
    buttons, lines = [], []
    for page in pages:
        if planned is not None:
            buttons.append(
                [
                    {
                        "text": f"📅 Đăng lúc {_when(planned)} · {page.name}"[:60],
                        "callback_data": f"qp:{video.id}:{page.id}",
                    }
                ]
            )
        slot = page_queue.next_slot(db, page, video)
        label = f" ({_when(slot)})" if slot else ""
        buttons.append([{"text": f"➕ Hàng chờ {page.name}{label}"[:60], "callback_data": f"qa:{video.id}:{page.id}"}])
        lines.append(
            f"• {html.escape(page.name)}: khung trống tiếp theo {_when(slot)}"
            if slot
            else f"• {html.escape(page.name)}: chưa có khung trống trong 48 giờ tới"
        )
    head = "Chưa hẹn giờ. "
    if planned is not None:
        head += f"Giờ trong kế hoạch: <b>{_when(planned)}</b>. "
    telegram.send_text(
        chat,
        text + f" {head}Hàng chờ xếp vào khung trống lúc bấm, giờ có thể đổi nếu có bài khác vào trước. "
        "Muốn giờ khác thì chọn trong app (Đăng bài).\n" + "\n".join(lines),
        buttons,
    )


def ask_reason(chat: int, video: Video) -> None:
    telegram.call(
        "sendMessage",
        {
            "chat_id": chat,
            "text": f"❌ Đã bỏ video {_name(video)} (#v{video.id}). Vì sao bỏ? Trả lời tin này để ghi lý do "
            "(không bắt buộc). Khôi phục được trong app.",
            "reply_markup": {"force_reply": True, "input_field_placeholder": "Lý do bỏ video"},
        },
    )


def _reason_reply(db: DbSession, message: dict, sender: int | None) -> bool:
    """A reply to "Vì sao bỏ?": the reason goes on the member's own rejection of that video."""
    asked = message.get("reply_to_message") or {}
    mark = REASON_MARK.search(asked.get("text") or "")
    if not mark or not (asked.get("from") or {}).get("is_bot"):
        return False
    user = db.scalar(select(User).where(User.telegram_chat_id == sender, User.is_active.is_(True)))
    event = (
        db.scalar(
            select(VideoEvent)
            .where(
                VideoEvent.video_id == int(mark.group(1)),
                VideoEvent.type == "rejected",
                VideoEvent.actor_user_id == user.id,
            )
            .order_by(VideoEvent.id.desc())
            .limit(1)
        )
        if user
        else None
    )
    if event is None:
        telegram.send_text(message["chat"]["id"], "Không tìm thấy lần bỏ video này để ghi lý do.")
        return True
    event.payload = {**(event.payload or {}), "reason": (message.get("text") or "").strip()[:500]}
    db.commit()
    telegram.send_text(message["chat"]["id"], "📝 Đã ghi lý do bỏ video.")
    return True


def button(db: DbSession, user: User, action: str, rest: str, chat: int) -> str:
    """The commands' buttons: `rv:<video>` shows a pending video, `qa:<video>:<page>` adds it to a Page's queue.
    Returns the short answer Telegram shows."""
    from . import routes_queue
    from .storage import get_storage

    parts = rest.split(":")
    if not all(part.isdigit() for part in parts):
        return "Nút này không còn dùng được"
    if action == "rv":
        video = db.get(Video, int(parts[0]))
        if video is None or video.review_status != review.PENDING or not video.mp4_key:
            return "Video này không còn chờ duyệt"
        telegram.send_review(db, get_storage(), chat, video)
        return "Đã gửi video"
    if action == "qp":
        return _plan_post(db, user, int(parts[0]), int(parts[1]), chat)
    try:
        body = routes_queue.AddBody(video_id=int(parts[0]), fanpage_id=int(parts[1]))
        added = routes_queue.add(body, SimpleNamespace(user_id=user.id), db)["item"]
    except ApiError as err:
        db.rollback()
        return err.message
    telegram.send_text(chat, f"➕ Đã thêm vào hàng chờ của <b>{html.escape(added['fanpage'])}</b>.")
    return "Đã thêm vào hàng chờ"


def _plan_post(db: DbSession, user: User, video_id: int, page_id: int, chat: int) -> str:
    """`qp:<video>:<page>`: the same as the plan tab's "Duyệt": post at the plan idea's time on the Page."""
    from .routes_videos import PublishBody, publish

    video = db.get(Video, video_id)
    when = plan_time(db, video) if video is not None else None
    if when is None:
        return "Video chưa có giờ trong kế hoạch, hoặc giờ đó đã qua"
    try:
        publish(video_id, PublishBody(fanpage_id=page_id, scheduled_at=when), SimpleNamespace(user_id=user.id), db)
        db.commit()
    except ApiError as err:
        db.rollback()
        return err.message
    telegram.send_text(chat, f"📅 Đã hẹn đăng lúc <b>{_when(when)}</b>.")
    return "Đã hẹn giờ"


# --- The group's daily summary ---


def group_summary(db: DbSession, at: datetime | None = None) -> bool:
    """At 21:00 Vietnam time, once a day, the team's day in the shared group (TELEGRAM_CHAT_ID on the api and worker):
    numbers and the day's best video, nobody's own work. Returns whether it was sent."""
    group = config.telegram_group_chat_id()
    at = at or now()
    local = at.astimezone(VIETNAM)
    if not group or local.hour < SUMMARY_HOUR:
        return False
    day = local.date().isoformat()
    row = db.get(AppSetting, SUMMARY_KEY)
    if row is not None and row.value == day:
        return False
    if row is None:
        row = AppSetting(key=SUMMARY_KEY, value=day)
        db.add(row)
    else:
        row.value = day
    db.commit()  # marked first: a failed send is not repeated every round
    start, end = _day_bounds(at)
    lines = [f"🌙 <b>Tổng kết ngày {start:%d/%m}</b>", overview(db, at).split("\n", 1)[1]]
    best = db.execute(
        select(Video, Fanpage, PostMetrics.views)
        .join(Publication, Publication.video_id == Video.id)
        .join(PostMetrics, PostMetrics.publication_id == Publication.id)
        .outerjoin(Fanpage, Fanpage.id == Publication.fanpage_id)
        .where(
            PostMetrics.window == "latest",
            PostMetrics.views.is_not(None),
            Publication.published_at >= at - timedelta(days=2),
        )
        .order_by(PostMetrics.views.desc())
        .limit(1)
    ).first()
    if best is not None:
        video, page, views = best
        where = f" ({html.escape(page.name)})" if page else ""
        lines.append(f"🔥 Video nhiều view nhất 48 giờ qua: <b>{html.escape(_name(video))}</b>{where}, {views:,} view")
    try:
        telegram.send_text(int(group), "\n".join(lines))
    except (telegram.TelegramError, ValueError) as err:
        log.warning("Group summary not sent: %s", err)
        return False
    return True
