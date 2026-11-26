"""A video's content strategy and its script by beat ("Chiến lược & Kịch bản theo nhịp",
docs/decisions/2026-11-26-strategy-beats.md).

`videos.strategy` is `{content_type, audience, pain_point, promise}`; `videos.beats` a list of
`{id, type, start, end, text, scene_ids, alt_hooks?, items?, affiliate_product_id?}`. Muse writes them through MCP
(`set_video_strategy`), a member edits them on the video page. They describe the script; the video itself is still its
scenes, so a beat's text reaches the MP4 only through the scene it names (see `changed_texts`).
"""

import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .errors import ApiError
from .models import Scene, Video

# Content types and their default beats (the owner's spec, 2026-11-26), by code.
CONTENT_TYPES = {
    "hook_pain_solution": ("Hook – Nỗi đau – Giải pháp", ["hook", "pain", "solution", "cta"]),
    "listicle": ("Danh sách (Top N)", ["hook", "item", "cta"]),
    "myth_buster": ("Đính chính hiểu lầm", ["hook", "myth", "truth", "proof", "cta"]),
    "before_after": ("Trước – Sau", ["hook", "before", "turning_point", "after", "cta"]),
    "story": ("Kể chuyện", ["hook", "setup", "conflict", "resolution", "cta"]),
}
BEAT_TYPES = {
    "hook": "Hook",
    "pain": "Nỗi đau",
    "solution": "Giải pháp",
    "item": "Món",
    "myth": "Hiểu lầm",
    "truth": "Sự thật",
    "proof": "Bằng chứng",
    "before": "Trước",
    "after": "Sau",
    "turning_point": "Bước ngoặt",
    "setup": "Mở đầu",
    "conflict": "Xung đột",
    "resolution": "Giải quyết",
    "cta": "Kêu gọi",
}
MAX_BEATS = 20
MAX_FIELD = 300
MAX_TEXT = 600
MAX_ALT_HOOKS = 5
MAX_ITEMS = 10
MAX_SECONDS = 180


def catalog() -> dict:
    return {
        "content_types": [
            {"code": code, "name": name, "beats": beats} for code, (name, beats) in CONTENT_TYPES.items()
        ],
        "beat_types": [{"code": code, "name": name} for code, name in BEAT_TYPES.items()],
    }


def _bad(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def _text(value, limit: int, label: str) -> str:
    if not isinstance(value, str):
        raise _bad(f"{label} phải là chữ")
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip()
    if len(value) > limit:
        raise _bad(f"{label} dài quá {limit} ký tự")
    return value


def clean_strategy(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise _bad("Chiến lược không hợp lệ")
    code = raw.get("content_type")
    if code not in CONTENT_TYPES:
        raise _bad("Kiểu nội dung không có trong danh mục: " + ", ".join(CONTENT_TYPES))
    return {
        "content_type": code,
        "audience": _text(raw.get("audience", ""), MAX_FIELD, "Đối tượng"),
        "pain_point": _text(raw.get("pain_point", ""), MAX_FIELD, "Nỗi đau"),
        "promise": _text(raw.get("promise", ""), MAX_FIELD, "Lời hứa"),
    }


def clean_beats(db: DbSession, video: Video, raw: list) -> list[dict]:
    if not isinstance(raw, list) or len(raw) > MAX_BEATS:
        raise _bad(f"Tối đa {MAX_BEATS} nhịp")
    own = set(db.scalars(select(Scene.id).where(Scene.video_id == video.id)))
    out, seen = [], set()
    for number, beat in enumerate(raw, start=1):
        if not isinstance(beat, dict):
            raise _bad(f"Nhịp {number} không hợp lệ")
        beat_id = _text(beat.get("id", ""), 20, f"Mã nhịp {number}")
        if not beat_id or beat_id in seen:
            raise _bad(f"Mã nhịp {number} trống hoặc trùng")
        seen.add(beat_id)
        if beat.get("type") not in BEAT_TYPES:
            raise _bad(f"Loại nhịp {number} không có trong danh mục: " + ", ".join(BEAT_TYPES))
        start, end = beat.get("start"), beat.get("end")
        if not all(isinstance(n, int | float) and not isinstance(n, bool) for n in (start, end)):
            raise _bad(f"Nhịp {number} cần start và end là số giây")
        if not 0 <= start <= end <= MAX_SECONDS:
            raise _bad(f"Nhịp {number}: giây phải từ 0, start không lớn hơn end, tối đa {MAX_SECONDS}")
        scene_ids = beat.get("scene_ids", [])
        if not isinstance(scene_ids, list) or any(not isinstance(i, int) or isinstance(i, bool) for i in scene_ids):
            raise _bad(f"Nhịp {number}: scene_ids là danh sách ID cảnh của video")
        if foreign := [i for i in scene_ids if i not in own]:
            raise _bad(f"Nhịp {number}: cảnh {foreign[0]} không thuộc video này")
        cleaned = {
            "id": beat_id,
            "type": beat["type"],
            "start": round(float(start), 2),
            "end": round(float(end), 2),
            "text": _text(beat.get("text", ""), MAX_TEXT, f"Chữ nhịp {number}"),
            "scene_ids": scene_ids,
        }
        if beat["type"] == "hook":
            hooks = beat.get("alt_hooks", [])
            if not isinstance(hooks, list) or len(hooks) > MAX_ALT_HOOKS:
                raise _bad(f"Tối đa {MAX_ALT_HOOKS} hook thay thế")
            cleaned["alt_hooks"] = [_text(h, 200, "Hook thay thế") for h in hooks if str(h).strip()]
        if beat.get("items"):
            items = beat["items"]
            if not isinstance(items, list) or len(items) > MAX_ITEMS:
                raise _bad(f"Tối đa {MAX_ITEMS} món mỗi nhịp")
            cleaned["items"] = [_text(i, 100, "Món") for i in items]
        if beat["type"] == "cta":
            product = beat.get("affiliate_product_id")
            if product is not None and (not isinstance(product, int) or isinstance(product, bool)):
                raise _bad("affiliate_product_id phải là số hoặc null")
            cleaned["affiliate_product_id"] = product
        out.append(cleaned)
    return out


def changed_texts(old: list | None, new: list[dict]) -> list[tuple[int, str]]:
    """(scene id, new text) for each beat whose text a member changed and that names a scene: the first scene carries
    it, so the MP4 goes out of date and the render check asks for a new render."""
    before = {beat["id"]: beat for beat in old or []}
    return [
        (beat["scene_ids"][0], beat["text"])
        for beat in new
        if beat["scene_ids"] and beat["id"] in before and before[beat["id"]].get("text") != beat["text"]
    ]
