"""The 30-day topic plan of a topic group: its ideas and their status, its Backlog (ideas with no day yet), file
import, the posting time suggested for each idea, and the AI plan's prompt and parsing.

Like the script prompt, members edit only the plan prompt's text on /knowledge; the JSON format the AI answers in is
code, so an edited prompt can never break the parsing.
"""

import csv
import io
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from functools import cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import analytics
from .claude import ClaudeError, fill_placeholders
from .models import Fanpage, Job, KnowledgeTopic, PostMetrics, Publication, TopicPlanItem, Video
from .ownership import ensure_none_of_others

log = logging.getLogger(__name__)

PLAN_DAYS = 30
MIN_PER_DAY = 1
MAX_PER_DAY = 10
# The AI writes 10 days per call: a whole month in one answer would be cut off by the output limit.
DAYS_PER_CALL = 10
MAX_TOPIC_LENGTH = 300  # what a video's Chủ đề may hold (routes_videos.MAX_TOPIC_LENGTH)
MAX_PAIN_GROUP_LENGTH = 100
MAX_PAIN_LENGTH = 1000
MAX_HOOK_LENGTH = 500
MAX_IDEAS = PLAN_DAYS * MAX_PER_DAY
MAX_BACKLOG = 300
MAX_POST_TIMES = MAX_PER_DAY
MAX_FILE_BYTES = 1_000_000
# Vietnam has no daylight saving time, so a fixed offset is its time zone.
VIETNAM = timezone(timedelta(hours=7))

GROUP_PLACEHOLDER = "[Chủ đề nhóm]"
PER_DAY_PLACEHOLDER = "[Số video mỗi ngày]"

# Read from the linked video and its posts, never stored: "Chờ đăng" means the video has an MP4 and no post yet,
# as on the video lists ("Xong" said nothing about posting, 2026-11-12).
STATUS_LABELS = {
    "idea": "Ý tưởng",
    "started": "Đã tạo video",
    "scripted": "Đã viết kịch bản",
    "done": "Chờ đăng",
    "scheduled": "Đã lên lịch",
    "posted": "Đã đăng",
}

OUTPUT_FORMAT = """\
ĐỊNH DẠNG ĐẦU RA (bắt buộc): chỉ trả về đúng một object JSON, không kèm chữ nào khác, không bọc trong ```.
Object có trường "days": danh sách các ngày được yêu cầu, mỗi ngày có "day" (số ngày) và "ideas" (các ý tưởng của ngày).
Mỗi ý tưởng có:
- "topic": chủ đề video, một câu tối đa 25 từ (dùng làm chủ đề khi viết kịch bản);
- "pain_group": tên nhóm nỗi đau, 2–6 từ, viết giống nhau cho mọi ý tưởng cùng nhóm;
- "pain": nỗi đau cụ thể của người xem (họ sợ gì, đã thử gì, hiểu sai gì), 1–2 câu, tối đa 40 từ;
- "hook": góc hook cho 3 giây đầu, 1 câu tối đa 20 từ.

Ví dụ (một ngày, hai ý tưởng):
{
  "days": [
    {"day": 1, "ideas": [
      {"topic": "5 món sáng giúp ổn định huyết áp cho người hay chóng mặt, làm ngay từ mai",
       "pain_group": "Huyết áp và tim mạch",
       "pain": "Sợ tai biến khi huyết áp lên xuống thất thường, đã bỏ muối nhưng vẫn chóng mặt buổi sáng.",
       "hook": "Bỏ muối rồi mà sáng nào cũng chóng mặt? Có thể bạn quên bữa sáng này."},
      {"topic": "7 thói quen trước khi ngủ giúp ngủ sâu hơn, gửi ngay cho bố mẹ",
       "pain_group": "Mất ngủ",
       "pain": "Nằm trằn trọc đến 2 giờ sáng, uống thuốc ngủ thì sợ lệ thuộc.",
       "hook": "Thức giấc lúc 2 giờ sáng không phải do tuổi già."}
    ]}
  ]
}"""


class PlanError(ValueError):
    """A file or an idea that cannot be used; the message is shown to members."""


class PlanOutputError(ValueError):
    pass


@dataclass(frozen=True)
class Idea:
    day: int | None  # None: the Backlog
    topic: str
    pain_group: str = ""
    pain: str = ""
    hook: str = ""


@cache
def default_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "plan_default.txt").read_text(encoding="utf-8").rstrip("\n")


def today() -> date:
    return datetime.now(VIETNAM).date()


def day_of(start: date | None, on: date) -> int | None:
    """Which plan day `on` is (1 is the start date); below 1 or above 30 when the plan has not started or is over."""
    return (on - start).days + 1 if start else None


def item_status(video: Video | None, post: Publication | None = None) -> str:
    if video is None:
        return "idea"
    if post is not None:
        return "posted" if post.status == "published" else "scheduled"
    if video.mp4_key:
        return "done"
    return "scripted" if video.has_script else "started"


def day_label(day: int | None) -> str:
    return f"ngày {day}" if day is not None else "Backlog"


def check_post_times(times: list[str]) -> list[str]:
    """1 to MAX_POST_TIMES times of day, "HH:MM", in order; the message is shown to members."""
    if not 1 <= len(times) <= MAX_POST_TIMES:
        raise PlanError(f"Cần từ 1 đến {MAX_POST_TIMES} giờ đăng")
    cleaned = []
    for value in times:
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
        if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
            raise PlanError(f"Giờ đăng “{value}” phải có dạng HH:MM")
        cleaned.append(f"{int(match.group(1)):02d}:{match.group(2)}")
    return sorted(cleaned)


def suggested_post_at(topic: KnowledgeTopic, item: TopicPlanItem, now: datetime | None = None) -> datetime | None:
    """When the idea's video is meant to go out: its plan day, at the group's posting time of its place in the day
    (the last time for a place past them). None in the Backlog, without a start date, or once that time is past."""
    if item.day is None or topic.plan_start_date is None or not topic.plan_post_times:
        return None
    times = topic.plan_post_times
    hour, minute = (int(part) for part in times[min(item.position, len(times)) - 1].split(":"))
    on = topic.plan_start_date + timedelta(days=item.day - 1)
    at = datetime(on.year, on.month, on.day, hour, minute, tzinfo=VIETNAM)
    return at if at > (now or datetime.now(VIETNAM)) else None


def topic_key(topic: str) -> str:
    """Two ideas are the same topic when they differ only in case, spacing or Unicode form."""
    return " ".join(unicodedata.normalize("NFC", topic).split()).casefold()


def clean(value: str, limit: int, label: str, cut: bool = False) -> str:
    """One line of text; too long refuses, or is cut when `cut` (the AI's answer is repaired, not refused)."""
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if len(value) > limit:
        if not cut:
            raise PlanError(f"{label} dài quá {limit} ký tự")
        value = value[:limit].rstrip()
    return value


def make_idea(
    day: int | None, topic: str, pain_group: str = "", pain: str = "", hook: str = "", cut: bool = False
) -> Idea:
    if day is not None and not 1 <= day <= PLAN_DAYS:
        raise PlanError(f"Ngày phải từ 1 đến {PLAN_DAYS}")
    topic = clean(topic, MAX_TOPIC_LENGTH, "Chủ đề", cut)
    if not topic:
        raise PlanError("Thiếu chủ đề")
    return Idea(
        day=day,
        topic=topic,
        pain_group=clean(pain_group, MAX_PAIN_GROUP_LENGTH, "Nhóm nỗi đau", cut),
        pain=clean(pain, MAX_PAIN_LENGTH, "Nỗi đau", cut),
        hook=clean(hook, MAX_HOOK_LENGTH, "Góc hook", cut),
    )


def check_plan(ideas: list[Idea]) -> tuple[list[str], list[str]]:
    """Errors stop a plan from being saved; warnings are shown and do not."""
    errors, warnings = [], []
    if not ideas:
        errors.append("Không có ý tưởng nào")
    undated = [idea.topic for idea in ideas if idea.day is None]
    if undated:
        errors.append(f"{len(undated)} ý tưởng chưa có ngày (chỉ thêm được vào Backlog), ví dụ “{undated[0]}”")
    counts: dict[int, int] = {}
    for idea in ideas:
        if idea.day is not None:
            counts[idea.day] = counts.get(idea.day, 0) + 1
    errors += [
        f"Ngày {day} có {count} ý tưởng, tối đa {MAX_PER_DAY}" for day, count in counts.items() if count > MAX_PER_DAY
    ]
    first_day: dict[str, int | None] = {}
    for idea in ideas:
        key = topic_key(idea.topic)
        if key in first_day:
            errors.append(f"Chủ đề trùng: “{idea.topic}” ({day_label(first_day[key])} và {day_label(idea.day)})")
        else:
            first_day[key] = idea.day
    if ideas:
        missing = [day for day in range(1, PLAN_DAYS + 1) if day not in counts]
        if missing:
            warnings.append(f"Chưa có ý tưởng cho ngày {', '.join(map(str, missing))}")
        few = [day for day, count in sorted(counts.items()) if count < MIN_PER_DAY]
        if few:
            warnings.append(
                f"Ngày {', '.join(map(str, few))} có dưới {MIN_PER_DAY} ý tưởng (nên có {MIN_PER_DAY}–{MAX_PER_DAY})"
            )
    return errors, warnings


# --- File import (JSON or CSV) ---

FIELD_NAMES = {
    "day": ("day", "ngay", "ngay_thu"),
    "topic": ("topic", "chu_de", "title", "tieu_de", "y_tuong", "idea"),
    "pain_group": ("pain_group", "nhom_noi_dau", "nhom"),
    "pain": ("pain", "noi_dau", "pain_point", "noi_dau_nguoi_xem", "noi_dau_cu_the"),
    "hook": ("hook", "goc_hook", "hook_angle", "angle"),
}
FIELD_OF = {name: field for field, names in FIELD_NAMES.items() for name in names}
# Where a JSON file keeps its days or ideas, and where a day keeps its ideas.
LIST_NAMES = ("days", "ngay", "ke_hoach", "plan", "ideas", "y_tuong", "items")
DAY_IDEAS_NAMES = ("ideas", "y_tuong", "items", "videos")


def _name(raw: object) -> str:
    """A column or key name without accents, case or punctuation: "Nhóm nỗi đau" is nhom_noi_dau."""
    text = unicodedata.normalize("NFD", str(raw)).replace("đ", "d").replace("Đ", "D")
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _value(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(_value(item) for item in value if _value(item))
    if isinstance(value, bool) or value is None:
        return ""
    return str(value) if isinstance(value, (str, int, float)) else ""


def _day(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    match = re.fullmatch(r"\D*?(\d{1,3})", str(value).strip()) if isinstance(value, str) else None
    return int(match.group(1)) if match else None


def _idea(raw: dict, day: object, where: str, cut: bool = False) -> Idea:
    fields: dict[str, object] = {}
    for key, value in raw.items():
        field = FIELD_OF.get(_name(key))
        if field and field not in fields:
            fields[field] = value
    raw_day = fields.get("day", day)
    # No day at all is an idea for the Backlog; a day that is not a number is a mistake.
    number = None if raw_day is None or _value(raw_day).strip() == "" else _day(raw_day)
    if number is None and not (raw_day is None or _value(raw_day).strip() == ""):
        raise PlanError(f"{where}: ngày không phải số")
    try:
        return make_idea(
            number,
            _value(fields.get("topic")),
            _value(fields.get("pain_group")),
            _value(fields.get("pain")),
            _value(fields.get("hook")),
            cut,
        )
    except PlanError as err:
        message = str(err)
        raise PlanError(f"{where}: {message[:1].lower()}{message[1:]}") from None


def _nested(item: dict, names: tuple[str, ...]) -> list | None:
    return next((value for key, value in item.items() if _name(key) in names and isinstance(value, list)), None)


def _walk(items: list, cut: bool = False) -> tuple[list[Idea], list[str]]:
    """Each item is a day with its ideas, or one idea with its own day."""
    ideas, errors = [], []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"Mục {index}: không phải object")
            continue
        inner = _nested(item, DAY_IDEAS_NAMES)
        if inner is None:
            rows = [(item, None, f"Mục {index}")]
        else:
            day = next((value for key, value in item.items() if FIELD_OF.get(_name(key)) == "day"), None)
            rows = [(idea, day, f"Ngày {day if day is not None else '?'}, ý {n}") for n, idea in enumerate(inner, 1)]
        for raw, day, where in rows:
            if not isinstance(raw, dict):
                errors.append(f"{where}: không phải object")
                continue
            try:
                ideas.append(_idea(raw, day, where, cut))
            except PlanError as err:
                errors.append(str(err))
    return ideas, errors


def _json_items(data: object) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        found = _nested(data, LIST_NAMES)
        if found is not None:
            return found
        # {"1": [...], "Ngày 2": [...]}: the day is the key.
        days = [(_day(key), value) for key, value in data.items()]
        if days and all(number is not None and isinstance(value, list) for number, value in days):
            return [{"day": number, "ideas": value} for number, value in days]
    raise PlanError("File JSON phải có danh sách “days” (mỗi ngày có “ideas”) hoặc danh sách ý tưởng")


def _parse_json(text: str) -> tuple[list[Idea], list[str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise PlanError(f"JSON lỗi cú pháp ở dòng {err.lineno}, cột {err.colno}") from None
    return _walk(_json_items(data))


def _parse_csv(text: str) -> tuple[list[Idea], list[str]]:
    # The delimiter the header uses most: Excel saves Vietnamese CSV files with ";" as often as with ",".
    first_line = text.splitlines()[0]
    delimiter = max((",", ";", "\t"), key=first_line.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader, None)
    columns = [FIELD_OF.get(_name(name)) for name in header or []]
    if "topic" not in columns:
        raise PlanError("File CSV cần dòng tiêu đề có cột chủ đề (topic), thêm cột ngày (day) nếu là kế hoạch")
    ideas, errors = [], []
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        raw = {field: value for field, value in zip(columns, row, strict=False) if field}
        try:
            ideas.append(_idea(raw, None, f"Dòng {reader.line_num}"))
        except PlanError as err:
            errors.append(str(err))
    return ideas, errors


def parse_file(filename: str, data: bytes) -> tuple[list[Idea], list[str]]:
    """The ideas of a JSON or CSV file, and one message per row that could not be read."""
    if len(data) > MAX_FILE_BYTES:
        raise PlanError(f"File lớn quá {MAX_FILE_BYTES // 1_000_000} MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise PlanError("File phải là văn bản UTF-8 (JSON hoặc CSV)") from None
    if not text.strip():
        raise PlanError("File trống")
    is_json = filename.lower().endswith(".json") or text.lstrip()[:1] in ("{", "[")
    ideas, errors = _parse_json(text) if is_json else _parse_csv(text)
    if len(ideas) > MAX_BACKLOG:
        raise PlanError(f"File có {len(ideas)} ý tưởng, tối đa {MAX_BACKLOG}")
    return sorted(ideas, key=lambda idea: (idea.day is None, idea.day or 0)), errors


# --- The plan as saved ---


def items_of(db: DbSession, topic_id: int) -> list[TopicPlanItem]:
    return list(
        db.scalars(
            select(TopicPlanItem)
            .where(TopicPlanItem.knowledge_topic_id == topic_id)
            .order_by(TopicPlanItem.day, TopicPlanItem.position, TopicPlanItem.id)
        )
    )


def _on(day: int | None):
    return TopicPlanItem.day.is_(None) if day is None else TopicPlanItem.day == day


def day_count(db: DbSession, topic_id: int, day: int | None) -> int:
    """The ideas of one day, or of the Backlog when `day` is None."""
    return db.scalar(
        select(func.count()).select_from(TopicPlanItem).where(TopicPlanItem.knowledge_topic_id == topic_id, _on(day))
    )


def renumber(db: DbSession, topic_id: int, day: int | None) -> None:
    db.flush()
    rows = db.scalars(
        select(TopicPlanItem)
        .where(TopicPlanItem.knowledge_topic_id == topic_id, _on(day))
        .order_by(TopicPlanItem.position, TopicPlanItem.id)
    ).all()
    for position, row in enumerate(rows, start=1):
        row.position = position


def replace_plan(db: DbSession, topic: KnowledgeTopic, ideas: list[Idea], user_id: int) -> None:
    """The 30 days become `ideas`; the Backlog stays, but for an idea the new plan now has on a day. An idea that keeps
    the topic of one that had a video keeps the video, so re-importing an adjusted plan does not lose what was made."""
    current = items_of(db, topic.id)
    linked = {topic_key(item.topic): item.video_id for item in current if item.video_id}
    planned = {topic_key(idea.topic) for idea in ideas}
    leaving = [item for item in current if item.day is not None or topic_key(item.topic) in planned]
    # The 30 days are replaced only when every idea that goes is the saving member's own (ownership.py).
    ensure_none_of_others(
        {"ý tưởng": sum(1 for item in leaving if item.created_by_id != user_id)}, "Kế hoạch 30 ngày của nhóm"
    )
    for item in leaving:
        db.delete(item)
    db.flush()
    positions: dict[int, int] = {}
    for idea in sorted(ideas, key=lambda idea: idea.day):
        positions[idea.day] = positions.get(idea.day, 0) + 1
        db.add(
            TopicPlanItem(
                knowledge_topic_id=topic.id,
                position=positions[idea.day],
                video_id=linked.pop(topic_key(idea.topic), None),
                created_by_id=user_id,
                updated_by_id=user_id,
                **asdict(idea),
            )
        )
    topic.plan_draft = None
    renumber(db, topic.id, None)


# How a previewed file is loaded (brief docs/specs/nap-ke-hoach-tuy-chon): "overwrite" is "Lưu kế hoạch" as before;
# the others leave the days the file does not name alone.
IMPORT_MODES = ("overwrite", "append", "next_empty", "replace_days")


class NotEnoughDays(PlanError):
    """ "Thêm vào ngày trống tiếp theo" with fewer empty days than the file has, unless asked to load what fits."""

    def __init__(self, empty: int, days: int):
        super().__init__(f"Còn {empty} ngày trống, file có {days} ngày")


def empty_days(items: list[TopicPlanItem]) -> list[int]:
    taken = {item.day for item in items}
    return [day for day in range(1, PLAN_DAYS + 1) if day not in taken]


def apply_import(
    db: DbSession, topic: KnowledgeTopic, ideas: list[Idea], mode: str, user_id: int, fit: bool = False
) -> dict:
    """Load checked, dated `ideas` in one of IMPORT_MODES and say what changed: the days newly filled, given more
    ideas, replaced or emptied, the ideas skipped because the plan already has their topic (a topic is never twice in
    a plan) or their day is full, and the file's days that found no room. An idea whose topic waits in the Backlog
    moves onto its day with its video. Nothing changes when it refuses."""
    by_day: dict[int, list[Idea]] = {}
    for idea in ideas:
        by_day.setdefault(idea.day, []).append(idea)
    current = items_of(db, topic.id)
    had = {item.day for item in current if item.day is not None}
    report: dict = {
        "mode": mode,
        "filled": [],
        "appended": [],
        "replaced": [],
        "emptied": [],
        "duplicates": [],
        "full": [],
        "not_loaded": [],
        "placed": [],
    }
    if mode == "overwrite":
        replace_plan(db, topic, ideas, user_id)
        report["replaced"] = sorted(day for day in by_day if day in had)
        report["filled"] = sorted(day for day in by_day if day not in had)
        report["emptied"] = sorted(day for day in had if day not in by_day)
        report["days"] = sorted(set(by_day) | had)
        return report

    linked: dict[str, int] = {}
    if mode == "replace_days":
        leaving = [item for item in current if item.day in by_day]
        ensure_none_of_others(
            {"ý tưởng": sum(1 for item in leaving if item.created_by_id != user_id)}, "Các ngày sẽ thay"
        )
        linked = {topic_key(item.topic): item.video_id for item in leaving if item.video_id}
        for item in leaving:
            db.delete(item)
        db.flush()
        current = [item for item in current if item not in leaving]
    found = {topic_key(item.topic): item for item in current}

    def planned_elsewhere(idea: Idea) -> TopicPlanItem | None:
        item = found.get(topic_key(idea.topic))
        return item if item is not None and item.day is not None else None

    target = {day: day for day in by_day}
    if mode == "next_empty":
        # A day of the file whose every topic the plan already has takes no empty day.
        wanted = [day for day in sorted(by_day) if not all(planned_elsewhere(idea) for idea in by_day[day])]
        empty = empty_days(current)
        if len(wanted) > len(empty) and not fit:
            raise NotEnoughDays(len(empty), len(by_day))
        target = dict(zip(wanted, empty, strict=False))
        report["not_loaded"] = wanted[len(empty) :]

    counts: dict[int, int] = {}
    for item in current:
        if item.day is not None:
            counts[item.day] = counts.get(item.day, 0) + 1
    moved_from_backlog = False
    for file_day in sorted(by_day):
        day = target.get(file_day)
        before = counts.get(day, 0) if day is not None else 0
        added = 0
        for idea in by_day[file_day]:
            held = planned_elsewhere(idea)
            if held is not None:
                report["duplicates"].append({"topic": idea.topic, "day": day, "where": day_label(held.day)})
                continue
            if day is None:
                continue
            if counts.get(day, 0) >= MAX_PER_DAY:
                report["full"].append({"topic": idea.topic, "day": day})
                continue
            counts[day] = counts.get(day, 0) + 1
            fields = {**asdict(idea), "day": day}
            item = found.get(topic_key(idea.topic))
            if item is not None:  # waiting in the Backlog: it moves, keeping its maker and its video
                for name, value in fields.items():
                    setattr(item, name, value)
                item.position, item.updated_by_id = counts[day], user_id
                moved_from_backlog = True
            else:
                item = TopicPlanItem(
                    knowledge_topic_id=topic.id,
                    position=counts[day],
                    video_id=linked.pop(topic_key(idea.topic), None),
                    created_by_id=user_id,
                    updated_by_id=user_id,
                    **fields,
                )
                db.add(item)
            found[topic_key(idea.topic)] = item
            added += 1
        if day is None:
            continue
        if mode == "replace_days" and day in had:
            report["replaced"].append(day)
        elif added and before:
            report["appended"].append(day)
        elif added:
            report["filled"].append(day)
        if added and mode == "next_empty":
            report["placed"].append([file_day, day])
    if moved_from_backlog:
        renumber(db, topic.id, None)
    report["days"] = sorted({*report["filled"], *report["appended"], *report["replaced"]})
    return report


def add_to_backlog(db: DbSession, topic: KnowledgeTopic, ideas: list[Idea], user_id: int) -> tuple[int, int]:
    """Ideas into the Backlog, after what it holds; a topic the plan or the Backlog already has is skipped. Returns
    how many were added and skipped."""
    taken = {topic_key(item.topic) for item in items_of(db, topic.id)}
    position = day_count(db, topic.id, None)
    added = 0
    for idea in ideas:
        key = topic_key(idea.topic)
        if key in taken:
            continue
        taken.add(key)
        position += 1
        added += 1
        db.add(
            TopicPlanItem(
                knowledge_topic_id=topic.id,
                day=None,
                position=position,
                topic=idea.topic,
                pain_group=idea.pain_group,
                pain=idea.pain,
                hook=idea.hook,
                created_by_id=user_id,
                updated_by_id=user_id,
            )
        )
    return added, len(ideas) - added


def item_payload(
    item: TopicPlanItem, video: Video | None, post: Publication | None = None, topic: KnowledgeTopic | None = None
) -> dict:
    status = item_status(video, post)
    post_at = (post.published_at or post.scheduled_at) if post is not None else None
    suggested = suggested_post_at(topic, item) if topic is not None and status != "posted" else None
    return {
        "id": item.id,
        "created_by_id": item.created_by_id,  # only they delete it
        "knowledge_topic_id": item.knowledge_topic_id,
        "day": item.day,
        "position": item.position,
        "topic": item.topic,
        "pain_group": item.pain_group,
        "pain": item.pain,
        "hook": item.hook,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "video_id": item.video_id,
        # When its post went out or is set to; else when the plan means it to go out (Vietnam time, ISO).
        "post_at": post_at.isoformat() if post_at else None,
        "suggested_post_at": suggested.isoformat() if suggested else None,
    }


def _videos(db: DbSession, items: list[TopicPlanItem]) -> dict[int, Video]:
    ids = [item.video_id for item in items if item.video_id]
    return {video.id: video for video in db.scalars(select(Video).where(Video.id.in_(ids)))} if ids else {}


def _posts(db: DbSession, items: list[TopicPlanItem]) -> dict[int, Publication]:
    """Each video's post that counts for its idea: a published one first, else the earliest one set for later."""
    ids = [item.video_id for item in items if item.video_id]
    if not ids:
        return {}
    rows = db.scalars(
        select(Publication).where(
            Publication.video_id.in_(ids),
            (Publication.status == "published")
            | (Publication.status.in_(("scheduled", "pending")) & Publication.scheduled_at.is_not(None)),
        )
    )
    best: dict[int, Publication] = {}
    for post in rows:
        rank = (post.status != "published", post.published_at or post.scheduled_at)
        kept = best.get(post.video_id)
        if kept is None or rank < (kept.status != "published", kept.published_at or kept.scheduled_at):
            best[post.video_id] = post
    return best


def numbers_48h(db: DbSession, items: list[TopicPlanItem]) -> dict[int, list[dict]]:
    """Each video's Facebook posts that went live, with their 48-hour numbers and how they compare to their Page's
    median, by video id. Only the `48h` reading: `latest` is never put in its place, so posts are compared at the same
    age. The medians are read once for all of them; two queries load the posts and their readings."""
    ids = [item.video_id for item in items if item.video_id]
    if not ids:
        return {}
    posts = db.execute(
        select(Publication, Fanpage.name)
        .outerjoin(Fanpage, Fanpage.id == Publication.fanpage_id)
        .where(
            Publication.video_id.in_(ids),
            Publication.platform == "facebook",
            Publication.published_at.is_not(None),
        )
        .order_by(Publication.published_at, Publication.id)
    ).all()
    if not posts:
        return {}
    readings = {
        (mark.publication_id, mark.window): mark
        for mark in db.scalars(
            select(PostMetrics).where(PostMetrics.publication_id.in_([post.id for post, _ in posts]))
        )
    }
    marks = {publication_id: mark for (publication_id, window), mark in readings.items() if window == "48h"}
    by_page = analytics.medians(db)
    found: dict[int, list[dict]] = {}
    for post, page_name in posts:
        mark = marks.get(post.id)
        views, shares = (mark.views, mark.shares) if mark else (None, None)
        found.setdefault(post.video_id, []).append(
            {
                "publication_id": post.id,
                "fanpage_name": page_name or "",
                "views": views,
                "shares": shares,
                # The newest reading, shown beside the 48-hour one and never in its place.
                "latest_views": latest.views if (latest := readings.get((post.id, "latest"))) else None,
                "measured_at": mark.measured_at.isoformat() if mark else None,
                **analytics.of_post(post, views, shares, by_page),
            }
        )
    return found


def payloads(db: DbSession, items: list[TopicPlanItem], topic: KnowledgeTopic | None = None) -> list[dict]:
    videos, posts = _videos(db, items), _posts(db, items)
    if topic is None and items:
        topic = db.get(KnowledgeTopic, items[0].knowledge_topic_id)
    return [item_payload(item, videos.get(item.video_id), posts.get(item.video_id), topic) for item in items]


def plan_job(db: DbSession, topic_id: int) -> Job | None:
    """The topic's plan job still to show: one queued or running, else the last one if it failed."""
    job = db.scalar(
        select(Job).where(Job.knowledge_topic_id == topic_id, Job.kind == "plan").order_by(Job.id.desc()).limit(1)
    )
    return job if job is not None and job.status in ("queued", "running", "failed") else None


def plan_payload(db: DbSession, topic: KnowledgeTopic) -> dict:
    rows = items_of(db, topic.id)
    items = payloads(db, rows, topic)
    numbers = numbers_48h(db, rows)
    for item in items:
        item["posts"] = numbers.get(item["video_id"], []) if item["video_id"] else []
    job = plan_job(db, topic.id)
    return {
        "topic_id": topic.id,
        "name": topic.name,
        "start_date": topic.plan_start_date.isoformat() if topic.plan_start_date else None,
        "today_day": day_of(topic.plan_start_date, today()),
        "per_day": topic.plan_per_day,
        "post_times": topic.plan_post_times,
        "prompt": topic.plan_prompt or default_prompt(),
        "default_prompt": default_prompt(),
        "items": items,
        "made": sum(1 for item in items if item["status"] != "idea" and item["day"] is not None),
        "job": {"id": job.id, "status": job.status, "error": job.error, "error_detail": job.error_detail}
        if job
        else None,
        "draft": topic.plan_draft,
        # Compared against on the cards, so the goal lives in one place (analytics.SHARE_GOAL).
        "share_goal": analytics.SHARE_GOAL,
        "video_target": topic.video_target,
        "video_count": db.scalar(select(func.count()).select_from(Video).where(Video.knowledge_topic_id == topic.id)),
    }


def today_payload(db: DbSession, topic_ids: set[int]) -> list[dict]:
    """Each of these topic groups (the member's own) whose plan has a today: its ideas of today, for "Tạo video" and
    the progress banner, and the last day that has a video for every idea from today on ("đã chuẩn bị trước đến ngày
    ..."). All its topics come too, so the dialog can tell a topic outside the plan."""
    on = today()
    groups = []
    running = select(KnowledgeTopic).where(
        KnowledgeTopic.plan_start_date.is_not(None), KnowledgeTopic.id.in_(topic_ids)
    )
    for topic in db.scalars(running.order_by(KnowledgeTopic.id)):
        day = day_of(topic.plan_start_date, on)
        if not 1 <= day <= PLAN_DAYS:
            continue
        items = items_of(db, topic.id)
        if not items:
            continue
        groups.append(
            {
                "topic_id": topic.id,
                "name": topic.name,
                "day": day,
                "ideas": payloads(db, [item for item in items if item.day == day], topic),
                "prepared_through": prepared_through(items, day),
                "topics": [item.topic for item in items],
            }
        )
    return groups


def prepared_through(items: list[TopicPlanItem], today_day: int) -> int | None:
    """The last day, from today on, up to which every day has ideas and each of them a video; None if today has not."""
    last = None
    for day in range(today_day, PLAN_DAYS + 1):
        ideas = [item for item in items if item.day == day]
        if not ideas or any(item.video_id is None for item in ideas):
            break
        last = day
    return last


def idea_of_video(db: DbSession, video_id: int) -> TopicPlanItem | None:
    return db.scalar(select(TopicPlanItem).where(TopicPlanItem.video_id == video_id))


# --- The AI plan ("Tạo bằng AI") ---


def build_prompt(
    template: str,
    group: str,
    per_day: int,
    banned_words: list[str],
    first: int,
    last: int,
    start: date | None,
    taken: list[str],
) -> str:
    body = fill_placeholders(
        template or default_prompt(),
        [(GROUP_PLACEHOLDER, "Chủ đề nhóm", group), (PER_DAY_PLACEHOLDER, "Số video mỗi ngày", str(per_day))],
    )
    parts = [body]
    if banned_words:
        quoted = ", ".join(f'"{word}"' for word in banned_words)
        parts.append(f"Từ cấm, không được dùng trong chủ đề, nỗi đau và hook: {quoted}.")
    scope = (
        f"Lần này chỉ lập ngày {first} đến ngày {last}, mỗi ngày đúng {per_day} ý tưởng; các ngày khác lập ở lượt khác."
    )
    if start:
        weekend = [day for day in range(first, last + 1) if (start + timedelta(days=day - 1)).weekday() >= 5]
        if weekend:
            scope += f" Ngày cuối tuần (thứ Bảy, Chủ nhật) trong các ngày này: {', '.join(map(str, weekend))}."
    parts.append(scope)
    if taken:
        listed = "\n".join(f"- {topic}" for topic in taken)
        parts.append(f"Các chủ đề đã có trong kế hoạch, không lặp lại và không viết na ná:\n{listed}")
    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)


def parse_output(raw: str, first: int, last: int, taken: set[str]) -> list[Idea]:
    """The ideas of days `first` to `last`. Small slips are repaired: long text is cut, extra ideas, other days and
    topics already taken are dropped; a day left with no idea makes the answer unusable."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise PlanOutputError("câu trả lời không có object JSON")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as err:
        raise PlanOutputError(f"JSON lỗi cú pháp: {err.msg} (dòng {err.lineno}, cột {err.colno})") from None
    try:
        found, _ = _walk(_json_items(data), cut=True)
    except PlanError as err:
        raise PlanOutputError(str(err)) from None
    ideas, seen, counts = [], set(taken), dict.fromkeys(range(first, last + 1), 0)
    for idea in found:
        key = topic_key(idea.topic)
        if idea.day not in counts or counts[idea.day] >= MAX_PER_DAY or key in seen:
            continue
        seen.add(key)
        counts[idea.day] += 1
        ideas.append(idea)
    missing = [day for day, count in counts.items() if not count]
    if missing:
        raise PlanOutputError(f"thiếu ý tưởng cho ngày {', '.join(map(str, missing))}")
    return ideas


def generate(
    topic: KnowledgeTopic, label: str, on_call: Callable[[], None], call: Callable[[str, str], str]
) -> list[Idea]:
    """The whole month, 10 days per call; each call is told the topics already chosen. An unusable answer is asked
    once more, then the plan fails with the raw answer as the detail."""
    ideas: list[Idea] = []
    for first in range(1, PLAN_DAYS + 1, DAYS_PER_CALL):
        last = min(first + DAYS_PER_CALL - 1, PLAN_DAYS)
        taken = [idea.topic for idea in ideas]
        prompt = build_prompt(
            topic.plan_prompt,
            topic.name,
            topic.plan_per_day,
            topic.banned_words,
            first,
            last,
            topic.plan_start_date,
            taken,
        )
        for attempt in (1, 2):
            raw = call(prompt, f"{label} ngày {first}-{last}")
            on_call()
            try:
                ideas += parse_output(raw, first, last, {topic_key(name) for name in taken})
                break
            except PlanOutputError as err:
                log.warning(
                    "Plan answer unusable for %s, days %d-%d (attempt %d): %s", label, first, last, attempt, err
                )
                problem = err
        else:
            raise ClaudeError(
                f"AI trả kế hoạch ngày {first}–{last} không đúng định dạng ({problem}), đã thử lại 1 lần",
                f"Câu trả lời thô:\n{raw[:8000]}",
            )
    return ideas


def draft_payload(job_id: int, ideas: list[Idea]) -> dict:
    """What the AI wrote, kept on the topic until a member saves or drops it."""
    errors, warnings = check_plan(ideas)
    return {
        "job_id": job_id,
        "created_at": datetime.now(VIETNAM).isoformat(),
        "ideas": [asdict(idea) for idea in ideas],
        "errors": errors,
        "warnings": warnings,
    }


def enqueue(db: DbSession, topic_id: int, user_id: int, retry_of_id: int | None = None) -> bool:
    """Queue "Tạo bằng AI"; False when the topic group already has one queued or running (the partial unique index
    is the guard), after rolling the transaction back."""
    db.add(
        Job(
            knowledge_topic_id=topic_id,
            kind="plan",
            status="queued",
            created_by_id=user_id,
            retry_of_id=retry_of_id,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True
