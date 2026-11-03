"""The 30-day topic plan of a topic group: its ideas and their status, file import, and the AI plan's prompt and parsing.

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

from .claude import ClaudeError, fill_placeholders
from .models import Job, KnowledgeTopic, TopicPlanItem, Video

log = logging.getLogger(__name__)

PLAN_DAYS = 30
MIN_PER_DAY = 3
MAX_PER_DAY = 5
# The AI writes 10 days per call: a whole month in one answer would be cut off by the output limit.
DAYS_PER_CALL = 10
MAX_TOPIC_LENGTH = 300  # what a video's Chủ đề may hold (routes_videos.MAX_TOPIC_LENGTH)
MAX_PAIN_GROUP_LENGTH = 100
MAX_PAIN_LENGTH = 1000
MAX_HOOK_LENGTH = 500
MAX_IDEAS = PLAN_DAYS * MAX_PER_DAY
MAX_FILE_BYTES = 1_000_000
# Vietnam has no daylight saving time, so a fixed offset is its time zone.
VIETNAM = timezone(timedelta(hours=7))

GROUP_PLACEHOLDER = "[Chủ đề nhóm]"
PER_DAY_PLACEHOLDER = "[Số video mỗi ngày]"

# Read from the linked video, never stored: "Xong" means the video has an MP4.
STATUS_LABELS = {
    "idea": "Ý tưởng",
    "started": "Đã tạo video",
    "scripted": "Đã viết kịch bản",
    "done": "Xong",
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
    day: int
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


def item_status(video: Video | None) -> str:
    if video is None:
        return "idea"
    if video.mp4_key:
        return "done"
    return "scripted" if video.has_script else "started"


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


def make_idea(day: int, topic: str, pain_group: str = "", pain: str = "", hook: str = "", cut: bool = False) -> Idea:
    if not 1 <= day <= PLAN_DAYS:
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
    counts: dict[int, int] = {}
    for idea in ideas:
        counts[idea.day] = counts.get(idea.day, 0) + 1
    errors += [
        f"Ngày {day} có {count} ý tưởng, tối đa {MAX_PER_DAY}" for day, count in counts.items() if count > MAX_PER_DAY
    ]
    first_day: dict[str, int] = {}
    for idea in ideas:
        key = topic_key(idea.topic)
        if key in first_day:
            errors.append(f"Chủ đề trùng: “{idea.topic}” (ngày {first_day[key]} và ngày {idea.day})")
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
    number = _day(fields.get("day", day))
    if number is None:
        raise PlanError(f"{where}: thiếu ngày hoặc ngày không phải số")
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
    if "day" not in columns or "topic" not in columns:
        raise PlanError("File CSV cần dòng tiêu đề có cột ngày và chủ đề (day, topic)")
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
    if len(ideas) > MAX_IDEAS:
        raise PlanError(f"File có {len(ideas)} ý tưởng, tối đa {MAX_IDEAS}")
    return sorted(ideas, key=lambda idea: idea.day), errors


# --- The plan as saved ---


def items_of(db: DbSession, topic_id: int) -> list[TopicPlanItem]:
    return list(
        db.scalars(
            select(TopicPlanItem)
            .where(TopicPlanItem.knowledge_topic_id == topic_id)
            .order_by(TopicPlanItem.day, TopicPlanItem.position, TopicPlanItem.id)
        )
    )


def day_count(db: DbSession, topic_id: int, day: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(TopicPlanItem)
        .where(TopicPlanItem.knowledge_topic_id == topic_id, TopicPlanItem.day == day)
    )


def renumber(db: DbSession, topic_id: int, day: int) -> None:
    db.flush()
    rows = db.scalars(
        select(TopicPlanItem)
        .where(TopicPlanItem.knowledge_topic_id == topic_id, TopicPlanItem.day == day)
        .order_by(TopicPlanItem.position, TopicPlanItem.id)
    ).all()
    for position, row in enumerate(rows, start=1):
        row.position = position


def replace_plan(db: DbSession, topic: KnowledgeTopic, ideas: list[Idea], user_id: int) -> None:
    """The whole plan becomes `ideas`. An idea that keeps the topic of one that had a video keeps the video, so
    re-importing an adjusted plan does not lose what was already made."""
    linked = {topic_key(item.topic): item.video_id for item in items_of(db, topic.id) if item.video_id}
    db.query(TopicPlanItem).filter(TopicPlanItem.knowledge_topic_id == topic.id).delete()
    db.flush()
    positions: dict[int, int] = {}
    for idea in sorted(ideas, key=lambda idea: idea.day):
        positions[idea.day] = positions.get(idea.day, 0) + 1
        db.add(
            TopicPlanItem(
                knowledge_topic_id=topic.id,
                position=positions[idea.day],
                video_id=linked.pop(topic_key(idea.topic), None),
                updated_by_id=user_id,
                **asdict(idea),
            )
        )
    topic.plan_draft = None


def item_payload(item: TopicPlanItem, video: Video | None) -> dict:
    status = item_status(video)
    return {
        "id": item.id,
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
    }


def _videos(db: DbSession, items: list[TopicPlanItem]) -> dict[int, Video]:
    ids = [item.video_id for item in items if item.video_id]
    return {video.id: video for video in db.scalars(select(Video).where(Video.id.in_(ids)))} if ids else {}


def payloads(db: DbSession, items: list[TopicPlanItem]) -> list[dict]:
    videos = _videos(db, items)
    return [item_payload(item, videos.get(item.video_id)) for item in items]


def plan_job(db: DbSession, topic_id: int) -> Job | None:
    """The topic's plan job still to show: one queued or running, else the last one if it failed."""
    job = db.scalar(
        select(Job).where(Job.knowledge_topic_id == topic_id, Job.kind == "plan").order_by(Job.id.desc()).limit(1)
    )
    return job if job is not None and job.status in ("queued", "running", "failed") else None


def plan_payload(db: DbSession, topic: KnowledgeTopic) -> dict:
    items = payloads(db, items_of(db, topic.id))
    job = plan_job(db, topic.id)
    return {
        "topic_id": topic.id,
        "name": topic.name,
        "start_date": topic.plan_start_date.isoformat() if topic.plan_start_date else None,
        "today_day": day_of(topic.plan_start_date, today()),
        "per_day": topic.plan_per_day,
        "prompt": topic.plan_prompt or default_prompt(),
        "default_prompt": default_prompt(),
        "items": items,
        "made": sum(1 for item in items if item["status"] != "idea"),
        "job": {"id": job.id, "status": job.status, "error": job.error, "error_detail": job.error_detail}
        if job
        else None,
        "draft": topic.plan_draft,
    }


def today_payload(db: DbSession) -> list[dict]:
    """Every topic group whose plan has a today: its ideas of today, for "Tạo video" and the progress banner. All
    its topics come too, so the dialog can tell a topic outside the plan."""
    on = today()
    groups = []
    for topic in db.scalars(select(KnowledgeTopic).where(KnowledgeTopic.plan_start_date.is_not(None))):
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
                "ideas": payloads(db, [item for item in items if item.day == day]),
                "topics": [item.topic for item in items],
            }
        )
    return groups


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
