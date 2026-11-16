"""Keeps Google Cloud Text-to-Speech within its monthly free tier ("Chỉ dùng mức miễn phí" on the "Giọng đọc Google"
card of Cài đặt › Mô hình AI).

Google gives each voice kind its own free characters a month and bills past them; it has no switch to stop there, so
the app counts the characters it sends, by kind, and refuses narration that would pass SAFETY of a kind's free tier
while the switch is on (the default). Characters are counted after Google answers, as Google bills only what it read,
and always, so the card shows the month's use even with the switch off. The month is Vietnam's calendar month; the
margin covers the hours by which it starts before Google's (Pacific time) month.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from .analytics import VIETNAM
from .models import AppSetting
from .tts import GOOGLE_PREFIX, TtsError, spoken_text

USAGE_KEY = "google_tts_usage"  # app_settings value: {"month": "2026-11", "chars": {kind: characters}}
FREE_ONLY_KEY = "google_tts_free_only"  # app_settings value: bool; absent means on
SAFETY = 0.9
# Google's free characters a month by voice kind (cloud.google.com/text-to-speech/pricing, 2026-11).
TIERS = {
    "standard": ("Standard", 4_000_000),
    "wavenet": ("WaveNet", 4_000_000),
    "neural2": ("Neural2", 1_000_000),
    "chirp_hd": ("Chirp-HD", 1_000_000),
}
OTHER = "other"  # a kind with no free tier known here: counted, and refused while the switch is on


def kind(voice_id: str) -> str:
    """The pricing kind of a Google voice, from its name ("google:vi-VN-Chirp3-HD-Achernar" → "chirp_hd")."""
    name = voice_id.removeprefix(GOOGLE_PREFIX).lower()
    if "chirp" in name and "hd" in name:
        return "chirp_hd"
    for found in ("neural2", "wavenet", "standard"):
        if f"-{found}-" in name:
            return found
    return OTHER


def characters(voice_text: str) -> int:
    """What Google bills for a text: its characters, spaces included, as the narration sends it."""
    return len(spoken_text(voice_text))


def limit(tier: str) -> int:
    return int(TIERS[tier][1] * SAFETY) if tier in TIERS else 0


def this_month() -> str:
    return datetime.now(VIETNAM).strftime("%Y-%m")


def free_only(db: DbSession) -> bool:
    setting = db.get(AppSetting, FREE_ONLY_KEY)
    return setting is None or setting.value is not False


def set_free_only(db: DbSession, enabled: bool, user_id: int) -> None:
    setting = db.get(AppSetting, FREE_ONLY_KEY)
    if setting is None:
        db.add(AppSetting(key=FREE_ONLY_KEY, value=enabled, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = enabled, user_id


def used(db: DbSession) -> dict[str, int]:
    """This month's characters by kind; empty once a new month starts."""
    setting = db.get(AppSetting, USAGE_KEY)
    value = setting.value if setting and isinstance(setting.value, dict) else {}
    if value.get("month") != this_month() or not isinstance(value.get("chars"), dict):
        return {}
    return {name: int(count) for name, count in value["chars"].items() if isinstance(count, int)}


def _number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def check(db: DbSession, voice_id: str, voice_text: str) -> None:
    """Refuses a narration that would take its kind past the safe share of the free tier, while the switch is on."""
    if not free_only(db):
        return
    tier = kind(voice_id)
    if tier not in TIERS:
        raise TtsError(
            "Loại giọng Google này không có mức miễn phí mà app biết, nên app không đọc để tránh bị tính phí: chọn "
            "giọng Standard, WaveNet, Neural2 hoặc Chirp-HD, hoặc tắt “Chỉ dùng mức miễn phí” ở Cài đặt › Mô hình AI"
        )
    before = used(db).get(tier, 0)
    if before + characters(voice_text) > limit(tier):
        raise TtsError(
            f"Giọng Google {TIERS[tier][0]} đã gần hết mức miễn phí tháng này ({_number(before)} / "
            f"{_number(limit(tier))} ký tự), app dừng để không bị tính phí: chọn loại giọng khác, đợi sang tháng, "
            "hoặc tắt “Chỉ dùng mức miễn phí” ở Cài đặt › Mô hình AI"
        )


def record(db: DbSession, voice_id: str, voice_text: str) -> None:
    """Adds a narration Google read to this month's count. The row is locked, so two jobs at once both count; the
    caller commits."""
    db.execute(insert(AppSetting).values(key=USAGE_KEY, value={}).on_conflict_do_nothing(index_elements=["key"]))
    setting = db.scalars(
        select(AppSetting)
        .where(AppSetting.key == USAGE_KEY)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    month = this_month()
    value = setting.value if isinstance(setting.value, dict) else {}
    counts = dict(value.get("chars") or {}) if value.get("month") == month else {}
    tier = kind(voice_id)
    counts[tier] = int(counts.get(tier, 0)) + characters(voice_text)
    setting.value = {"month": month, "chars": counts}


def payload(db: DbSession) -> dict:
    """What the card shows: the switch, and this month's use of each kind against its safe limit."""
    counts = used(db)
    usage = [
        {"kind": tier, "label": label, "used": counts.get(tier, 0), "limit": limit(tier)}
        for tier, (label, _) in TIERS.items()
    ]
    if counts.get(OTHER):
        usage.append({"kind": OTHER, "label": "Loại khác (tính phí)", "used": counts[OTHER], "limit": 0})
    return {"free_only": free_only(db), "month": datetime.now(VIETNAM).strftime("%m/%Y"), "usage": usage}
