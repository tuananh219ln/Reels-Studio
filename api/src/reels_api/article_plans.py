"""A Page's 30-day plan of article scripts ("Kế hoạch 30 ngày" on Bài viết; decisions 2026-11-15, "article plan").

One plan per Page: day 1 is its start date (Vietnam time), each day has `per_day` slots posted at `post_times`, and
every slot holds one script (hook, body, call to comment, hashtags, a photo brief and links, kind, topic group).
Scripts with no day wait in the plan's Backlog. "Tạo bài từ ô này" makes an article from a script; the slot is "Đã
dùng" while that article exists. A file (CSV or JSON) is read into a preview first (`preview_file`) and written only
when a member saves it (`apply_rows`), as the video plan's file is; the Backlog is kept.
"""

import csv
import io
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import articles, slot_comments
from .article_posts import comparable
from .models import (
    ARTICLE_KINDS,
    Article,
    ArticlePlan,
    ArticlePlanSlot,
    Fanpage,
    KnowledgeTopic,
    Publication,
)
from .plans import VIETNAM, check_post_times, today

PLAN_DAYS = 30
MIN_PER_DAY, MAX_PER_DAY = 1, 10
DEFAULT_TIMES = ["07:00", "11:30", "20:00"]
MAX_BACKLOG = 300
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
MAX_HOOK = 150
MAX_BODY = 2000
MAX_CTA = 300
MAX_BRIEF = 500
MAX_TONE = 500
MAX_AUDIENCE = 200
MAX_LINKS = 10
RECENT_DAYS = 60  # a hook like one posted on the Page this recently is a warning
SIMILAR = 0.8  # the share of words two hooks have in common to be "gần giống"

PLACEMENTS = ("by_day_slot", "fill_empty")
CONFLICTS = ("to_backlog", "overwrite", "skip")
STATUS_LABELS = {
    "unused": "Chưa dùng",
    "used": "Đã tạo bài",
    "scheduled": "Đã lên lịch",
    "posted": "Đã đăng",
    "skipped": "Bỏ qua",
}
# What a file may write in "format": an article kind's code, its label, or a common short name.
KIND_NAMES = {
    "meo": "meo",
    "meo vat": "meo",
    "kien thuc": "kien_thuc",
    "kien thuc ngan": "kien_thuc",
    "cau hoi": "cau_hoi",
    "cau hoi tuong tac": "cau_hoi",
    "tham do": "cau_hoi",
    "canh bao": "canh_bao",
    "nhac nho": "canh_bao",
    "tra loi binh luan": "tra_loi_binh_luan",
    "danh sach": "checklist",
    "tong hop": "checklist",
    "checklist": "checklist",
}
TEMPLATE_ROWS = [
    {
        "day": 1,
        "slot": 1,
        "hook": "Bữa sáng 10 phút cho dân văn phòng",
        "body": "Sáng nào cũng vội? Đây là 3 bữa sáng làm trong 10 phút mà vẫn đủ chất:\n1. Yến mạch ngâm sữa chua\n"
        "2. Bánh mì nguyên cám + trứng ốp\n3. Khoai lang luộc + sữa đậu nành",
        "cta": "Bạn hay ăn sáng món gì?",
        "hashtags": ["#ansang", "#suckhoe"],
        "image_brief": "Bàn ăn sáng gọn, ánh sáng tự nhiên",
        "image_urls": [],
        "format": "Mẹo",
        "topic_group": "Sức khỏe",
        "pinned_comments": [
            {"type": "cong_dung", "text": "Yến mạch giàu chất xơ, giúp no lâu và hỗ trợ tiêu hóa nhẹ nhàng hơn."},
            {"type": "cach_lam", "text": "Ngâm yến mạch với sữa chua qua đêm, sáng ra chỉ việc thêm trái cây."},
            {"type": "luu_y", "text": "Mỗi bữa khoảng 3–4 muỗng canh yến mạch là vừa, ăn nhiều dễ đầy bụng."},
            {"type": "nen_dung", "text": "Hợp với người hay bỏ bữa sáng, dân văn phòng cần bữa nhanh gọn."},
            {
                "type": "han_che",
                "text": "Người có bệnh dạ dày hoặc tiểu đường nên hỏi bác sĩ trước khi ăn thường xuyên.",
            },
        ],
        "pin_index": 0,
    },
    {
        "day": None,
        "slot": None,
        "hook": "Uống nước lúc nào là tốt nhất?",
        "body": "Nội dung bài…",
        "cta": "",
        "hashtags": [],
        "image_brief": "",
        "image_urls": [],
        "format": "Kiến thức ngắn",
        "topic_group": "Sức khỏe",
    },
]
COLUMNS = (
    "day",
    "slot",
    "hook",
    "body",
    "cta",
    "hashtags",
    "image_brief",
    "image_urls",
    "format",
    "topic_group",
    "cmt_1",
    "cmt_2",
    "cmt_3",
    "cmt_4",
    "cmt_5",
    "cmt_types",
    "pin_index",
)


class PlanFileError(ValueError):
    """A file that cannot be read at all; the message is shown to members."""


def plain(text: str) -> str:
    """Lower case without accents or extra spaces, so "Mẹo vặt" matches "meo vat"."""
    folded = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return " ".join("".join(char for char in folded if not unicodedata.combining(char)).lower().split())


def kind_of(name: str) -> str | None:
    """The article kind a file names, or None when it names none it knows."""
    key = plain(name).replace("_", " ")
    if not key:
        return None
    for code, label in articles.KIND_LABELS.items():
        if key in (code.replace("_", " "), plain(label)):
            return code
    return KIND_NAMES.get(key)


# --- The plan ---


def plan_of(db: DbSession, fanpage_id: int, lock: bool = False) -> ArticlePlan | None:
    query = select(ArticlePlan).where(ArticlePlan.fanpage_id == fanpage_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def day_today(plan: ArticlePlan) -> int | None:
    """Which day of the plan today is (1–30), or None before it starts or after it ends."""
    if plan.start_date is None:
        return None
    day = (today() - plan.start_date).days + 1
    return day if 1 <= day <= PLAN_DAYS else None


def slot_time(plan: ArticlePlan, day: int, slot: int) -> datetime | None:
    """When a slot is meant to go out: its day at the slot's posting time, Vietnam time."""
    if plan.start_date is None or slot > len(plan.post_times):
        return None
    hour, minute = (int(part) for part in plan.post_times[slot - 1].split(":"))
    on = plan.start_date + timedelta(days=day - 1)
    return datetime(on.year, on.month, on.day, hour, minute, tzinfo=VIETNAM)


def slots_of(db: DbSession, plan_id: int) -> list[ArticlePlanSlot]:
    return list(
        db.scalars(
            select(ArticlePlanSlot)
            .where(ArticlePlanSlot.plan_id == plan_id)
            .order_by(ArticlePlanSlot.day.nulls_last(), ArticlePlanSlot.slot, ArticlePlanSlot.id)
        )
    )


def backlog_count(db: DbSession, plan_id: int) -> int:
    return db.scalar(select(func.count()).where(ArticlePlanSlot.plan_id == plan_id, ArticlePlanSlot.day.is_(None))) or 0


def to_backlog(slot: ArticlePlanSlot) -> None:
    slot.day = slot.slot = None


def apply_settings(
    db: DbSession,
    plan: ArticlePlan,
    start_date: date | None,
    per_day: int,
    post_times: list[str],
    topic_group_ids: list[int],
    kind_mix: dict[str, int],
    tone: str,
    audience: str = "",
) -> int:
    """Checks and saves "Thiết lập"; with fewer posts a day, the scripts of the slots dropped go to the Backlog (never
    deleted). Returns how many moved. Raises ValueError with the reason."""
    if not MIN_PER_DAY <= per_day <= MAX_PER_DAY:
        raise ValueError(f"Số bài mỗi ngày phải từ {MIN_PER_DAY} đến {MAX_PER_DAY}")
    times = check_post_times(post_times)
    if len(times) != per_day:
        raise ValueError(f"Cần đúng {per_day} giờ đăng, mỗi giờ cho một bài")
    # check_post_times puts them in order of the day; the same time twice would make two slots one.
    if len(set(times)) != len(times):
        raise ValueError("Mỗi giờ đăng chỉ một lần")
    groups = list(dict.fromkeys(topic_group_ids))
    for group_id in groups:
        if db.get(KnowledgeTopic, group_id) is None:
            raise ValueError("Không tìm thấy nhóm chủ đề")
    mix = {}
    for kind, share in kind_mix.items():
        if kind not in ARTICLE_KINDS:
            raise ValueError("Dạng bài không hợp lệ")
        if not 0 <= share <= 100:
            raise ValueError("Tỉ lệ dạng bài phải từ 0% đến 100%")
        if share:
            mix[kind] = share
    if mix and sum(mix.values()) != 100:
        raise ValueError("Tỉ lệ các dạng bài phải cộng lại đúng 100%")
    tone = " ".join(tone.split())
    if len(tone) > MAX_TONE:
        raise ValueError(f"Giọng văn dài quá {MAX_TONE} ký tự")
    audience = " ".join(audience.split())
    if len(audience) > MAX_AUDIENCE:
        raise ValueError(f"Nhóm đối tượng dài quá {MAX_AUDIENCE} ký tự")
    moved = 0
    if plan.id is not None and per_day < plan.per_day:
        dropped = db.scalars(
            select(ArticlePlanSlot).where(ArticlePlanSlot.plan_id == plan.id, ArticlePlanSlot.slot > per_day)
        ).all()
        if backlog_count(db, plan.id) + len(dropped) > MAX_BACKLOG:
            raise ValueError(f"Backlog sẽ quá {MAX_BACKLOG} kịch bản: xoá bớt Backlog trước khi giảm số bài mỗi ngày")
        for slot in dropped:
            to_backlog(slot)
            moved += 1
    plan.start_date, plan.per_day, plan.post_times = start_date, per_day, times
    plan.topic_group_ids, plan.kind_mix, plan.tone, plan.audience = groups, mix, tone, audience
    return moved


# --- Status and payload ---


def _posts_by_article(db: DbSession, article_ids: list[int]) -> dict[int, list[Publication]]:
    found: dict[int, list[Publication]] = {}
    if not article_ids:
        return found
    for post in db.scalars(
        select(Publication).where(
            Publication.article_id.in_(article_ids), Publication.status.in_(("pending", "scheduled", "published"))
        )
    ):
        found.setdefault(post.article_id, []).append(post)
    return found


def slot_status(slot: ArticlePlanSlot, posts: list[Publication]) -> str:
    from .videos import is_published

    if slot.article_id is not None:
        if any(is_published(post) for post in posts):
            return "posted"
        if any(post.status == "scheduled" for post in posts):
            return "scheduled"
        return "used"
    return "skipped" if slot.skipped else "unused"


def slot_payload(slot: ArticlePlanSlot, plan: ArticlePlan, posts: list[Publication], groups: dict[int, str]) -> dict:
    code = slot_status(slot, posts)
    at = slot_time(plan, slot.day, slot.slot) if slot.day is not None else None
    return {
        "id": slot.id,
        "day": slot.day,
        "slot": slot.slot,
        "hook": slot.hook,
        "body": slot.body,
        "cta": slot.cta,
        "hashtags": slot.hashtags,
        "image_brief": slot.image_brief,
        "image_urls": slot.image_urls,
        "kind": slot.kind,
        "kind_label": articles.KIND_LABELS.get(slot.kind or ""),
        "knowledge_topic_id": slot.knowledge_topic_id,
        "group_name": groups.get(slot.knowledge_topic_id or 0),
        "keywords": slot.keywords,
        "source": slot.source,
        "skipped": slot.skipped,
        "status": code,
        "status_label": STATUS_LABELS[code],
        "article_id": slot.article_id,
        "post_at": at.isoformat() if at else None,
        "created_by_id": slot.created_by_id,
        **slot_comments.slot_fields(slot),
    }


def payload(db: DbSession, page: Fanpage, plan: ArticlePlan | None, user_id: int) -> dict:
    """The plan tab: the Page, its plan's settings and counts, its 30 days of slots and its Backlog."""
    base = {
        "fanpage": {"id": page.id, "name": page.name, "owner_id": page.owner_id},
        "can_edit": page.owner_id == user_id,
        "defaults": {"per_day": len(DEFAULT_TIMES), "post_times": DEFAULT_TIMES},
        "kinds": [{"value": value, "label": label} for value, label in articles.KIND_LABELS.items()],
    }
    if plan is None:
        return {**base, "plan": None, "slots": [], "backlog": []}
    slots = slots_of(db, plan.id)
    posts = _posts_by_article(db, [slot.article_id for slot in slots if slot.article_id is not None])
    groups = dict(db.execute(select(KnowledgeTopic.id, KnowledgeTopic.name)).all())
    rows = [slot_payload(slot, plan, posts.get(slot.article_id or 0, []), groups) for slot in slots]
    placed = [row for row in rows if row["day"] is not None and row["slot"] <= plan.per_day]
    filled = {(row["day"], row["slot"]) for row in placed}
    empty_days = sum(
        1 for day in range(1, PLAN_DAYS + 1) if any((day, s) not in filled for s in range(1, plan.per_day + 1))
    )
    return {
        **base,
        "plan": {
            "id": plan.id,
            "start_date": plan.start_date.isoformat() if plan.start_date else None,
            "end_date": (plan.start_date + timedelta(days=PLAN_DAYS - 1)).isoformat() if plan.start_date else None,
            "today_day": day_today(plan),
            "per_day": plan.per_day,
            "post_times": plan.post_times,
            "topic_group_ids": plan.topic_group_ids,
            "kind_mix": plan.kind_mix,
            "tone": plan.tone,
            "audience": plan.audience,
            "total": PLAN_DAYS * plan.per_day,
            "used": sum(1 for row in placed if row["status"] in ("used", "scheduled", "posted")),
            "scheduled": sum(1 for row in placed if row["status"] == "scheduled"),
            "posted": sum(1 for row in placed if row["status"] == "posted"),
            "empty_days": empty_days,
            "backlog": sum(1 for row in rows if row["day"] is None),
            # "Bình luận: 72/87 kịch bản đủ 5/5" over the scripts on the grid, and the "Tạo bình luận ghim" jobs
            # still queued or running.
            "comments": slot_comments.summary(placed),
            "comments_pending": slot_comments.progress(db, plan.id),
        },
        "slots": placed,
        "backlog": [row for row in rows if row["day"] is None],
    }


def next_unused(db: DbSession, plan: ArticlePlan) -> ArticlePlanSlot | None:
    """The script "Tạo bài viết" offers first: the earliest unused slot from today on (from day 1 before the plan
    starts), in day and slot order."""
    first = day_today(plan) or 1
    return db.scalar(
        select(ArticlePlanSlot)
        .where(
            ArticlePlanSlot.plan_id == plan.id,
            ArticlePlanSlot.day >= first,
            ArticlePlanSlot.slot <= plan.per_day,
            ArticlePlanSlot.article_id.is_(None),
            ArticlePlanSlot.skipped.is_(False),
        )
        .order_by(ArticlePlanSlot.day, ArticlePlanSlot.slot)
        .limit(1)
    )


def caption_of(slot: ArticlePlanSlot) -> str:
    """The article's caption from a script: the hook, the body, then the call to comment."""
    return "\n\n".join(part.strip() for part in (slot.hook, slot.body, slot.cta) if part.strip())


# --- Moving scripts ---


def cell(db: DbSession, plan_id: int, day: int, slot: int) -> ArticlePlanSlot | None:
    return db.scalar(
        select(ArticlePlanSlot).where(
            ArticlePlanSlot.plan_id == plan_id, ArticlePlanSlot.day == day, ArticlePlanSlot.slot == slot
        )
    )


def move(db: DbSession, plan: ArticlePlan, slot: ArticlePlanSlot, day: int | None, number: int | None) -> None:
    """To a day and slot (swapping with the script there, which goes where this one was) or to the Backlog."""
    if (day is None) != (number is None):
        raise ValueError("Cần cả ngày và khung giờ, hoặc để trống cả hai (Backlog)")
    if day is None:
        if slot.day is not None and backlog_count(db, plan.id) >= MAX_BACKLOG:
            raise ValueError(f"Backlog đã đủ {MAX_BACKLOG} kịch bản")
        to_backlog(slot)
        return
    if not 1 <= day <= PLAN_DAYS or not 1 <= number <= plan.per_day:
        raise ValueError(f"Ngày phải từ 1 đến {PLAN_DAYS}, khung giờ từ 1 đến {plan.per_day}")
    there = cell(db, plan.id, day, number)
    if there is not None and there.id != slot.id:
        old_day, old_slot = slot.day, slot.slot
        # The unique cell index is checked per row: free this one first.
        to_backlog(slot)
        db.flush()
        there.day, there.slot = old_day, old_slot
        db.flush()
    slot.day, slot.slot = day, number


# --- Files ---


@dataclass
class Row:
    """One script of a file as previewed: what it holds, where it goes and what is wrong with it."""

    row: int
    day: int | None = None
    slot: int | None = None
    hook: str = ""
    body: str = ""
    cta: str = ""
    hashtags: list[str] = field(default_factory=list)
    image_brief: str = ""
    image_urls: list[str] = field(default_factory=list)
    kind: str | None = None
    knowledge_topic_id: int | None = None
    # The kind and topic group as the file names them, so saving checks the same names again.
    format: str = ""
    topic_group: str = ""
    # "Bình luận ghim" as the file gives them (slot_comments.py), and which one is pinned.
    pinned_comments: list[dict] = field(default_factory=list)
    pin_index: int = 0
    # What saving does with it: "add", "skip_posted" or "skip_used" (the slot already has an article), or "skip".
    action: str = "add"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Where saving puts it: "day:slot", "backlog" or "skip", with why when it is not where the file says.
    target: str = ""
    note: str = ""

    @property
    def check(self) -> str:
        return "error" if self.errors else "warning" if self.warnings else "ok"


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return unicodedata.normalize("NFC", str(value).replace("\r\n", "\n")).strip()


def _number(value: object, label: str, errors: list[str]) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        errors.append(f"{label} không phải số")
        return None


def _list(value: object, separator: str) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return [part.strip() for part in _text(value).split(separator) if part.strip()]


def _records(filename: str, data: bytes) -> list[dict]:
    if len(data) > MAX_FILE_BYTES:
        raise PlanFileError("File quá 2 MB")
    suffix = Path(filename).suffix.lower()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise PlanFileError("File phải là UTF-8 (Excel: Lưu thành “CSV UTF-8”)") from None
    if suffix == ".json":
        try:
            loaded = json.loads(text)
        except ValueError as err:
            raise PlanFileError(f"File JSON không đọc được: {err}") from None
        if isinstance(loaded, dict):
            loaded = next((loaded[key] for key in ("rows", "slots", "items", "plan") if key in loaded), None)
        if not isinstance(loaded, list) or not all(isinstance(item, dict) for item in loaded):
            raise PlanFileError("File JSON phải là một danh sách kịch bản, mỗi kịch bản là một object")
        records = loaded
    elif suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "hook" not in [name.strip().lower() for name in reader.fieldnames]:
            raise PlanFileError("File CSV cần dòng tiêu đề với ít nhất cột hook và body (xem File mẫu)")
        records = [{(key or "").strip().lower(): value for key, value in row.items()} for row in reader]
    else:
        raise PlanFileError("Chỉ nhận file .csv hoặc .json")
    if not records:
        raise PlanFileError("File không có kịch bản nào")
    if len(records) > MAX_ROWS:
        raise PlanFileError(f"File có {len(records)} dòng, tối đa {MAX_ROWS}")
    return records


def _hook_words(text: str) -> set[str]:
    return set(re.findall(r"\w+", comparable(text)))


def _alike(a: set[str], b: set[str]) -> bool:
    return bool(a) and bool(b) and len(a & b) / len(a | b) >= SIMILAR


def recent_hooks(db: DbSession, fanpage_id: int) -> list[tuple[set[str], str]]:
    """The hooks of the articles posted or scheduled on the Page in the last RECENT_DAYS days, with their date."""
    since = datetime.now(VIETNAM) - timedelta(days=RECENT_DAYS)
    rows = db.execute(
        select(Article.caption, Publication.published_at, Publication.scheduled_at, Publication.created_at)
        .join(Publication, Publication.article_id == Article.id)
        .where(
            Publication.fanpage_id == fanpage_id,
            Publication.status.in_(("scheduled", "published")),
            Publication.created_at >= since,
        )
    ).all()
    found = []
    for caption, published, scheduled, created in rows:
        when = (published or scheduled or created).astimezone(VIETNAM)
        found.append((_hook_words(articles.hook_of(caption)), when.strftime("%d/%m")))
    return found


def read_rows(db: DbSession, plan: ArticlePlan, records: list[dict]) -> list[Row]:
    """The file's scripts, each checked: errors (missing hook or body, too long, a kind or group that does not exist,
    the same day and slot twice) stop a row; a warning (a hook like one posted on the Page in 60 days) does not."""
    groups = {plain(name): topic_id for topic_id, name in db.execute(select(KnowledgeTopic.id, KnowledgeTopic.name))}
    recent = recent_hooks(db, plan.fanpage_id)
    rows: list[Row] = []
    seen: dict[tuple[int, int], int] = {}
    for index, record in enumerate(records, start=1):
        record = {str(key).strip().lower(): value for key, value in record.items()}
        row = Row(row=index)
        row.day = _number(record.get("day"), "Ngày", row.errors)
        row.slot = _number(record.get("slot"), "Khung", row.errors)
        row.hook, row.body, row.cta = _text(record.get("hook")), _text(record.get("body")), _text(record.get("cta"))
        row.image_brief = _text(record.get("image_brief"))
        row.hashtags = articles.clean_hashtags(_list(record.get("hashtags"), " "))
        row.image_urls = _list(record.get("image_urls"), "|")
        for value, limit, label in (
            (row.hook, MAX_HOOK, "hook"),
            (row.body, MAX_BODY, "body"),
            (row.cta, MAX_CTA, "cta"),
            (row.image_brief, MAX_BRIEF, "image_brief"),
        ):
            if len(value) > limit:
                row.errors.append(f"{label} dài quá {limit} ký tự")
        if not row.hook:
            row.errors.append("Thiếu hook")
        if not row.body:
            row.errors.append("Thiếu body")
        if len(row.image_urls) > MAX_LINKS:
            row.errors.append(f"Tối đa {MAX_LINKS} link ảnh")
        if any(not url.startswith(("http://", "https://")) for url in row.image_urls):
            row.errors.append("Link ảnh phải bắt đầu bằng http:// hoặc https://")
        kind_name = row.format = _text(record.get("format"))
        if kind_name:
            row.kind = kind_of(kind_name)
            if row.kind is None:
                row.errors.append(f"Dạng bài “{kind_name}” không tồn tại")
        group_name = row.topic_group = _text(record.get("topic_group"))
        if group_name:
            row.knowledge_topic_id = groups.get(plain(group_name))
            if row.knowledge_topic_id is None:
                row.errors.append(f"Nhóm chủ đề “{group_name}” không tồn tại")
        if row.slot is not None and row.day is None:
            row.errors.append("Có khung mà thiếu ngày")
        if row.slot is not None and not 1 <= row.slot <= plan.per_day:
            row.errors.append(f"Khung phải từ 1 đến {plan.per_day}")
        if row.day is not None and row.slot is not None and 1 <= row.day <= PLAN_DAYS:
            earlier = seen.get((row.day, row.slot))
            if earlier is not None:
                row.errors.append(f"Trùng ngày {row.day} · khung {row.slot} với dòng {earlier}")
            elif not row.errors:
                # A row that is not saved does not hold its slot against a later one.
                seen[(row.day, row.slot)] = index
        checked, shown = slot_comments.from_record(record)
        row.pinned_comments = [
            {"type": item.get("type"), "text": item.get("text")} for item in shown if isinstance(item, dict)
        ]
        row.errors.extend(checked.errors)
        row.warnings.extend(checked.warnings)
        if not checked.errors:
            row.pinned_comments, row.pin_index = slot_comments.stored(checked.items), checked.pin_index
        words = _hook_words(row.hook)
        like = next((when for hook, when in recent if _alike(words, hook)), None)
        if like is not None:
            row.warnings.append(f"Gần giống bài đăng {like}")
        rows.append(row)
    return rows


def _place(db: DbSession, plan: ArticlePlan, rows: list[Row], placement: str, conflict: str) -> None:
    """Fills each row's `target` and `note`: where saving puts it with this placement and conflict mode."""
    taken = {
        (slot.day, slot.slot): slot
        for slot in slots_of(db, plan.id)
        if slot.day is not None and slot.slot <= plan.per_day
    }
    posts = _posts_by_article(db, [slot.article_id for slot in taken.values() if slot.article_id is not None])
    claimed: set[tuple[int, int]] = set()
    free = [
        (day, number)
        for day in range((day_today(plan) or 1), PLAN_DAYS + 1)
        for number in range(1, plan.per_day + 1)
        if (day, number) not in taken
    ]
    for row in rows:
        row.action = "add"
        if row.errors:
            row.target, row.note, row.action = "skip", "Dòng lỗi không được lưu", "skip"
            continue
        if placement == "fill_empty":
            spot = next((cell for cell in free if cell not in claimed), None)
            if spot is None:
                row.target, row.note = "backlog", "Hết ô trống → Backlog"
            else:
                claimed.add(spot)
                row.target = f"{spot[0]}:{spot[1]}"
            continue
        if row.day is None or not 1 <= row.day <= PLAN_DAYS:
            row.target, row.note = "backlog", "Không có ngày (hoặc ngoài 1–30) → Backlog"
            continue
        number = row.slot
        if number is None:
            number = next(
                (n for n in range(1, plan.per_day + 1) if (row.day, n) not in taken and (row.day, n) not in claimed),
                None,
            )
            if number is None:
                row.target, row.note = "backlog", f"Ngày {row.day} đã kín → Backlog"
                continue
        spot = (row.day, number)
        claimed.add(spot)
        there = taken.get(spot)
        row.target = f"{spot[0]}:{spot[1]}"
        if there is None:
            continue
        if there.article_id is not None:
            # A slot an article was made from is never overwritten or moved: the file's row is skipped.
            done = slot_status(there, posts.get(there.article_id, []))
            row.target, row.action = "skip", "skip_posted" if done == "posted" else "skip_used"
            row.note = "Ô đã đăng → bỏ qua" if done == "posted" else "Ô đã tạo bài → bỏ qua"
        elif conflict == "skip":
            row.action = "skip"
            row.target, row.note = "skip", "Ô đã có kịch bản → bỏ qua dòng mới"
        elif conflict == "overwrite" and there.article_id is None:
            row.note = "Ghi đè kịch bản cũ"
        else:
            row.note = "Ô đã có kịch bản → cũ vào Backlog"


def preview_file(db: DbSession, plan: ArticlePlan, filename: str, data: bytes, placement: str, conflict: str) -> dict:
    rows = read_rows(db, plan, _records(filename, data))
    _place(db, plan, rows, placement, conflict)
    return preview_payload(rows)


def preview_payload(rows: list[Row]) -> dict:
    return {
        "rows": [{**asdict(row), "check": row.check} for row in rows],
        "counts": {
            "ok": sum(1 for row in rows if row.check == "ok"),
            "warning": sum(1 for row in rows if row.check == "warning"),
            "error": sum(1 for row in rows if row.check == "error"),
            "backlog": sum(1 for row in rows if row.target == "backlog"),
        },
    }


def apply_rows(
    db: DbSession,
    plan: ArticlePlan,
    rows: list[Row],
    placement: str,
    conflict: str,
    user_id: int,
    source: str = "import",
) -> dict:
    """ "Lưu kế hoạch": the rows without errors written where `_place` puts them; a script in a slot taken goes to the
    Backlog (or is replaced with "Ghi đè" when no article was made from it). Returns what was done."""
    _place(db, plan, rows, placement, conflict)
    report = {"placed": 0, "backlog": 0, "moved_to_backlog": 0, "replaced": 0, "skipped": 0}
    adding_to_backlog = sum(1 for row in rows if row.target == "backlog")
    for row in rows:
        if row.target == "skip":
            report["skipped"] += 1
            continue
        slot = ArticlePlanSlot(
            plan_id=plan.id,
            hook=row.hook,
            body=row.body,
            cta=row.cta,
            hashtags=row.hashtags,
            image_brief=row.image_brief,
            image_urls=row.image_urls,
            kind=row.kind,
            knowledge_topic_id=row.knowledge_topic_id,
            source=source,
            created_by_id=user_id,
        )
        if row.pinned_comments:
            # Checked again here, so a row changed in the browser cannot store what a file may not.
            checked = slot_comments.check(row.pinned_comments, row.pin_index, row.kind)
            if checked.errors:
                raise ValueError(f"Dòng {row.row}: " + "; ".join(checked.errors))
            slot_comments.set_comments(slot, checked, "import", edited=False)
        if row.target != "backlog":
            day, number = (int(part) for part in row.target.split(":"))
            there = cell(db, plan.id, day, number)
            if there is not None:
                if conflict == "overwrite" and there.article_id is None:
                    db.delete(there)
                    report["replaced"] += 1
                else:
                    to_backlog(there)
                    adding_to_backlog += 1
                    report["moved_to_backlog"] += 1
                db.flush()
            slot.day, slot.slot = day, number
            report["placed"] += 1
        else:
            report["backlog"] += 1
        db.add(slot)
    db.flush()
    if backlog_count(db, plan.id) > MAX_BACKLOG:
        raise ValueError(f"Backlog sẽ quá {MAX_BACKLOG} kịch bản: xoá bớt Backlog hoặc chọn “Bỏ qua dòng mới”")
    return report


def rows_from_payload(items: list[dict]) -> list[Row]:
    """The previewed rows sent back by "Lưu kế hoạch": only the fields a row holds; their checks were made by the
    preview and are made again by `check_rows`."""
    names = set(Row.__dataclass_fields__) - {"target", "note"}
    return [Row(**{key: value for key, value in item.items() if key in names}) for item in items]


def check_rows(db: DbSession, plan: ArticlePlan, rows: list[Row]) -> None:
    """The rows as saved are checked again: a row changed in the browser cannot slip past the rules."""
    records = [
        {
            "day": row.day,
            "slot": row.slot,
            "hook": row.hook,
            "body": row.body,
            "cta": row.cta,
            "hashtags": row.hashtags,
            "image_brief": row.image_brief,
            "image_urls": row.image_urls,
            "format": row.format,
            "topic_group": row.topic_group,
            "pinned_comments": row.pinned_comments,
            "pin_index": row.pin_index,
        }
        for row in rows
    ]
    for row, checked in zip(rows, read_rows(db, plan, records), strict=True):
        row.errors, row.warnings = checked.errors, checked.warnings
        row.hashtags, row.kind, row.knowledge_topic_id = checked.hashtags, checked.kind, checked.knowledge_topic_id
        row.pinned_comments, row.pin_index = checked.pinned_comments, checked.pin_index


def template(kind: str, group_name: str) -> tuple[bytes, str, str]:
    """ "Tải file mẫu": the file, its name and type."""
    rows = [{**row, "topic_group": group_name or row["topic_group"]} for row in TEMPLATE_ROWS]
    if kind == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2).encode(), "ke-hoach-bai-viet.json", "application/json"
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    for row in rows:
        comments = row.get("pinned_comments", [])
        cells = {f"cmt_{n}": comments[n - 1]["text"] if n <= len(comments) else "" for n in range(1, 6)}
        writer.writerow(
            {
                **{key: value for key, value in row.items() if key in COLUMNS},
                **cells,
                "cmt_types": "|".join(item.get("type") or "" for item in comments),
                "pin_index": row.get("pin_index", "") if comments else "",
                "day": row["day"] or "",
                "slot": row["slot"] or "",
                "hashtags": " ".join(row["hashtags"]),
                "image_urls": "|".join(row["image_urls"]),
            }
        )
    return ("\ufeff" + out.getvalue()).encode(), "ke-hoach-bai-viet.csv", "text/csv; charset=utf-8"
