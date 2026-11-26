"""A topic group's "QC & duyệt" (`knowledge_topics.qc_config`, migration 0136): the yellow ranges its videos are
checked against and whether the review gate asks for a title (docs/decisions/2026-11-26-per-group-qc.md).

- `title_required`: false lets a video with no title text be approved (Threads draws its title in the OP card).
- `total_seconds`: the script's total length that does not warn (script_rules.TOTAL_SECONDS_RANGE by default). The hard
  cap of script_rules.MAX_TOTAL_SECONDS stays the same for every group.
- `scene_count`: the number of content scenes that does not warn (script_rules.SCENE_COUNT_RANGE by default).
- `channel_seconds`: the MP4's length that does not warn (qc.SHORT–qc.LONG by default), judged when the video is read,
  from `videos.mp4_seconds`, so a video rendered before the group's range changed follows the new one.

The loudness target stays one for every group on purpose: it is the platforms' (qc.TARGET_LUFS).
A group with nothing set (None) checks as every group did before.
"""

from .qc import LONG, SHORT, TOO_SHORT
from .script_rules import MAX_TOTAL_SECONDS, SCENE_COUNT_RANGE, TOTAL_SECONDS_RANGE

RANGES = {
    "total_seconds": (TOTAL_SECONDS_RANGE, MAX_TOTAL_SECONDS, "Độ dài kịch bản"),
    "scene_count": (SCENE_COUNT_RANGE, 30, "Số cảnh nội dung"),
    "channel_seconds": ((int(SHORT), int(LONG)), 300, "Độ dài MP4"),
}
FIELDS = ("title_required", *RANGES)


class ConfigError(ValueError):
    pass


def defaults() -> dict:
    return {"title_required": True} | {
        field: {"min": low, "max": high} for field, ((low, high), _, _) in RANGES.items()
    }


def of(stored: dict | None) -> dict:
    """The group's settings, every field present: the defaults where it set nothing."""
    config = defaults()
    for field in FIELDS:
        if stored and stored.get(field) is not None:
            config[field] = stored[field]
    return config


def is_set(stored: dict | None) -> bool:
    return of(stored) != defaults()


def range_of(config: dict, field: str) -> tuple[float, float]:
    return config[field]["min"], config[field]["max"]


def _range(value: object, field: str) -> dict:
    _, limit, label = RANGES[field]
    if not isinstance(value, dict) or set(value) != {"min", "max"}:
        raise ConfigError(f"{label} phải có min và max")
    low, high = value["min"], value["max"]
    for number in (low, high):
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ConfigError(f"{label} phải là số")
    if not 0 <= low <= high <= limit:
        raise ConfigError(f"{label} phải từ 0 đến {limit:g}, min không lớn hơn max")
    if field == "channel_seconds" and low < TOO_SHORT:
        raise ConfigError(f"{label} tối thiểu {TOO_SHORT:g} giây")
    as_number = int if field == "scene_count" else float
    if field == "scene_count" and (low != int(low) or high != int(high)):
        raise ConfigError(f"{label} phải là số nguyên")
    low, high = as_number(low), as_number(high)
    return {"min": int(low) if low == int(low) else low, "max": int(high) if high == int(high) else high}


def clean(value: dict | None) -> dict | None:
    """What is saved from a form or a tool: every field checked; only the fields that differ from the defaults are
    kept, and nothing different saves None, so a later change of a default still reaches the group."""
    if not value:
        return None
    unknown = set(value) - set(FIELDS)
    if unknown:
        raise ConfigError(f"Không có mục {', '.join(sorted(unknown))} trong QC & duyệt")
    base = defaults()
    kept: dict = {}
    if value.get("title_required") is not None:
        if not isinstance(value["title_required"], bool):
            raise ConfigError("Bắt tiêu đề phải là đúng hoặc sai")
        if value["title_required"] != base["title_required"]:
            kept["title_required"] = value["title_required"]
    for field in RANGES:
        if value.get(field) is not None:
            checked = _range(value[field], field)
            if checked != base[field]:
                kept[field] = checked
    return kept or None


def text(config: dict) -> str:
    """A line for a member or an assistant: how the group is checked."""
    total, scenes, channel = (range_of(config, field) for field in RANGES)
    title = "bắt tiêu đề" if config["title_required"] else "không bắt tiêu đề"
    return (
        f"{title}; kịch bản {total[0]:g}–{total[1]:g} giây, {scenes[0]:g}–{scenes[1]:g} cảnh; "
        f"MP4 {channel[0]:g}–{channel[1]:g} giây"
    )
