"""A topic group's "Chữ & phụ đề": the text look its new videos take over their maker's defaults, the AI's suggested
looks for it ("AI gợi ý", a job), and the AI's pick for each video when the group asks for one ("AI chọn kiểu chữ
cho từng video", in the same call that writes the script)."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from .claude import ClaudeError, ScriptOutputError, json_object
from .models import Job, KnowledgeTopic
from .plans import VIETNAM
from .video_options import CAPTIONS, CHOICES, COLORS, LOOK_FIELDS, OptionError, clean

JOB_KIND = "text_look"
# What "Chữ & phụ đề" holds (Cài đặt › Thiết lập mặc định's card of that name): the text boxes' look and captions.
FIELDS = (*LOOK_FIELDS, "captions")
MAX_SUGGESTIONS = 3
MAX_NAME_LENGTH = 60
MAX_REASON_LENGTH = 300
# How much of the group's script prompt the suggestion call reads: enough for its audience and tone.
PROMPT_EXCERPT = 1500

# Plain words for each value, so the AI chooses by meaning, not by code names.
VALUE_NOTES = {
    "text_style": 'box = hộp màu (đặt "box_color", "text_color", "accent_color" bằng mã #RRGGBB), none = không hộp, '
    'chữ có viền (màu viền là "box_color"); dùng "box" hoặc "none"',
    "title_style": 'same = tiêu đề giống các cảnh, yellow = tiêu đề hộp vàng (khi "title_text_style" là "same")',
    "title_text_style": "same = theo title_style; hoặc một kiểu như text_style cho riêng tiêu đề",
    "box_opacity": "auto = theo kiểu, solid = đặc, soft = hơi trong (88%), clear = trong (70%), none = không nền",
    "text_size": "large = lớn, medium = vừa, small = nhỏ",
    "title_text_size": "large = lớn, medium = vừa, small = nhỏ",
    "text_case": "upper = viết HOA hết, keep = giữ chữ như kịch bản viết",
    "title_text_case": "upper = viết HOA hết, keep = giữ chữ như kịch bản viết",
    "captions": "off = không phụ đề, phrase = phụ đề theo cụm lời đọc, word = phụ đề tô vàng từng từ đang đọc",
}


def _field_lines() -> str:
    lines = []
    for name in FIELDS:
        if name in COLORS:
            named = ", ".join(value for value in COLORS[name])
            lines.append(f'- "{name}": {named} hoặc mã màu "#RRGGBB" ("auto" = màu sẵn của kiểu)')
        else:
            values = CAPTIONS if name == "captions" else CHOICES[name]
            note = VALUE_NOTES.get(name, "")
            lines.append(f'- "{name}": một trong {", ".join(values)}' + (f" ({note})" if note else ""))
    return "\n".join(lines)


LOOK_RULES = f"""Các trường của "look" (chỉ đưa trường muốn đổi; trường không đưa giữ như mặc định):
{_field_lines()}
Video dọc 9:16 cho Reels/TikTok, chữ phải dễ đọc trên ảnh bất kỳ trong 1–2 giây; người xem nhóm này đọc trên điện
thoại. Chữ đánh dấu (*từ*) dùng accent_color để nổi bật."""

# Added to the script prompt when the group's "AI chọn kiểu chữ cho từng video" is on (jobs.script_prompt).
SCRIPT_FORMAT = f"""KIỂU CHỮ CHO VIDEO NÀY (bắt buộc): thêm vào object JSON trường "text_look": object "look" như dưới, chọn
cho hợp với nội dung, cảm xúc và người xem của video này (không cần giống video khác của nhóm).
{LOOK_RULES}"""


def clean_look(values: object) -> dict:
    """A look a member saved: only the text fields, every one valid, or OptionError."""
    if not isinstance(values, dict):
        raise OptionError("Kiểu chữ không hợp lệ")
    unknown = [name for name in values if name not in FIELDS]
    if unknown:
        raise OptionError(f"Không có tuỳ chọn chữ “{unknown[0]}”")
    return clean(values)


# The named box styles older than "Kiểu hộp chữ" (the studio now picks "Không hộp" or a box of chosen colours): an
# AI that names one gets the same box as colours, so the editor shows what will be drawn (reels_render.textbox).
NAMED_BOXES = {
    "yellow": {"box_color": "#FFD60A", "text_color": "#111111", "accent_color": "#E10600"},
    "white": {"box_color": "#FFFFFF", "text_color": "#111111", "accent_color": "#E10600"},
    "dark": {"box_color": "#111111", "text_color": "#FFFFFF", "accent_color": "#FFD60A", "box_opacity": "soft"},
    "red": {"box_color": "#E10600", "text_color": "#FFFFFF", "accent_color": "#FFD60A"},
}


def loose_look(values: object) -> dict:
    """A look the AI wrote: its valid text fields only, anything else left out silently; a named box style becomes
    a box of its colours (NAMED_BOXES), colours the AI gave itself kept."""
    if not isinstance(values, dict):
        return {}
    values = dict(values)
    for prefix in ("", "title_"):
        named = NAMED_BOXES.get(values.get(f"{prefix}text_style"))
        if named:
            values[f"{prefix}text_style"] = "box"
            for name, value in named.items():
                values.setdefault(f"{prefix}{name}", value)
    return valid_fields(values)


def valid_fields(values: object) -> dict:
    """The valid text fields of a stored look, anything else left out."""
    if not isinstance(values, dict):
        return {}
    look = {}
    for name, value in values.items():
        if name not in FIELDS:
            continue
        try:
            look.update(clean({name: value}))
        except OptionError:
            continue
    return look


def group_look(group: KnowledgeTopic | None) -> dict:
    """The group's own look, valid values only; {} when it has none (its videos take their maker's)."""
    return valid_fields(group.text_look) if group is not None and group.text_look else {}


def suggest_prompt(group: KnowledgeTopic, current: dict) -> str:
    excerpt = (group.script_prompt or "").strip()[:PROMPT_EXCERPT]
    hint = (group.photo_hint or "").strip()
    return f"""Bạn là người thiết kế chữ cho video ngắn. Nhóm chủ đề "{group.name}" làm video dọc 9:16 cho Facebook Reels
và TikTok. Hãy đề xuất {MAX_SUGGESTIONS} phong cách chữ và phụ đề KHÁC HẲN nhau, sáng tạo nhưng dễ đọc, hợp với
người xem và giọng của nhóm.

Prompt viết kịch bản của nhóm (trích):
<prompt>
{excerpt or "(chưa có)"}
</prompt>
Ảnh của nhóm: {hint or "(không có gợi ý)"}
Kiểu chữ nhóm đang dùng: {current or "(theo mặc định của người tạo video)"}

{LOOK_RULES}

Chỉ trả về một object JSON, không giải thích gì thêm:
{{"options": [{{"name": "tên ngắn của phong cách, tối đa 6 từ", "reason": "1–2 câu vì sao hợp với nhóm",
"look": {{...}}}}]}}"""


def parse_suggestions(raw: str) -> list[dict]:
    """The AI's options with a valid look each; none usable raises ScriptOutputError."""
    data = json_object(raw)
    items = data.get("options")
    options = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        look = loose_look(item.get("look"))
        if not look:
            continue
        name = " ".join(str(item.get("name") or "").split())[:MAX_NAME_LENGTH] or f"Phong cách {len(options) + 1}"
        reason = " ".join(str(item.get("reason") or "").split())[:MAX_REASON_LENGTH]
        options.append({"name": name, "reason": reason, "look": look})
        if len(options) == MAX_SUGGESTIONS:
            break
    if not options:
        raise ScriptOutputError("không có phong cách chữ nào dùng được")
    return options


def generate(
    group: KnowledgeTopic, label: str, on_call: Callable[[], None], call: Callable[[str, str], str]
) -> list[dict]:
    """Asked once more when the answer is unusable, then given up with the raw answer as the detail."""
    prompt = suggest_prompt(group, group_look(group))
    for _attempt in (1, 2):
        raw = call(prompt, label)
        on_call()
        try:
            return parse_suggestions(raw)
        except ScriptOutputError as err:
            problem = err
    raise ClaudeError(
        f"AI trả gợi ý kiểu chữ không đúng định dạng ({problem}), đã thử lại 1 lần", f"Câu trả lời thô:\n{raw[:8000]}"
    )


def suggestions_payload(job_id: int, options: list[dict]) -> dict:
    return {"job_id": job_id, "created_at": datetime.now(VIETNAM).isoformat(), "options": options}


def enqueue(db: DbSession, topic_id: int, user_id: int, retry_of_id: int | None = None) -> bool:
    """Queue "AI gợi ý" for the group's text; False when one is already queued or running (the partial unique index
    is the guard), after rolling the transaction back."""
    db.add(
        Job(knowledge_topic_id=topic_id, kind=JOB_KIND, status="queued", created_by_id=user_id, retry_of_id=retry_of_id)
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def job_of(db: DbSession, topic_id: int) -> Job | None:
    """The group's suggestion job still to show: one queued or running, else the last one if it failed."""
    job = db.scalar(
        select(Job).where(Job.knowledge_topic_id == topic_id, Job.kind == JOB_KIND).order_by(Job.id.desc()).limit(1)
    )
    return job if job is not None and job.status in ("queued", "running", "failed") else None


def job_payload(job: Job | None) -> dict | None:
    if job is None:
        return None
    return {"id": job.id, "status": job.status, "error": job.error}
