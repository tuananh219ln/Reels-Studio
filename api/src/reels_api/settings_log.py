"""The edit history of the team's shared settings on Cài đặt › Mô hình AI and Nguồn tư liệu (edit_log.py), card by
card, as the pages show them. A key is never logged: only "…" and its last four characters, or None once removed
(docs/decisions/2026-11-09-settings-mine-and-shared.md)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import auto_photos, edit_log, image_providers, image_style, llm, routes_videos, source_keys
from .models import LlmProvider

# Card ids within each page's history, and the names the history shows for them.
AI_CARDS = {1: "AI viết kịch bản", 2: "Giọng đọc VieNeu"}
SOURCE_CARDS = {1: "Kho ảnh và video miễn phí", 2: "Dịch vụ AI"}
STOCK_KEYS = ("pixabay", "pexels", "unsplash")
SHORT_KEY = 12  # a shorter key shows no characters at all, as the page does


def tail(key: str | None) -> str | None:
    """What the history keeps of a key: "…" and its last four characters; None for no key."""
    if not key:
        return None
    return f"…{key[-4:]}" if len(key) >= SHORT_KEY else "…"


def _source_key(db: DbSession, name: str) -> str | None:
    """The key saved on the page (not the server's .env one, which members do not change)."""
    return tail(source_keys._saved(db, name))


def _llm_card(db: DbSession) -> dict[str, Any]:
    rows = {row.id: row for row in db.scalars(select(LlmProvider))}
    values: dict[str, Any] = {"active": llm.BY_ID[llm.active_id(db)].name}
    for preset in llm.PRESETS:
        row = rows.get(preset.id)
        values[f"{preset.id}.base_url"] = row.base_url if row else ""
        values[f"{preset.id}.model"] = row.model if row else ""
        values[f"{preset.id}.key"] = f"…{row.key_tail}" if row and row.key_encrypted else None
    return values


def snapshot(db: DbSession) -> dict[tuple[str, int], dict[str, Any]]:
    """Every card of both pages, as JSON values: (entity type, card id) → {field: value}."""
    stock: dict[str, Any] = {"auto_photos": auto_photos.enabled(db)}
    off = routes_videos.stock_turned_off(db)
    for source in routes_videos.STOCK_SOURCES:
        stock[f"{source}.enabled"] = source not in off
        if source in STOCK_KEYS:
            stock[f"{source}.key"] = _source_key(db, source)
    return {
        (edit_log.SETTINGS_AI, 1): _llm_card(db),
        (edit_log.SETTINGS_AI, 2): {"vieneu.key": _source_key(db, "vieneu")},
        (edit_log.SETTINGS_SOURCES, 1): stock,
        (edit_log.SETTINGS_SOURCES, 2): {
            "ai_provider": image_providers.saved(db),
            "ai_style": image_style.get(db),
            "gemini.key": _source_key(db, "gemini"),
            "cloudflare.key": _source_key(db, "cloudflare"),
            "elevenlabs.key": _source_key(db, "elevenlabs"),
        },
    }


def record(db: DbSession, before: dict[tuple[str, int], dict[str, Any]], user_id: int) -> None:
    """Logs what changed since `before`, one entry per card that changed; the caller commits."""
    db.flush()
    names = {edit_log.SETTINGS_AI: AI_CARDS, edit_log.SETTINGS_SOURCES: SOURCE_CARDS}
    for (entity_type, card), values in snapshot(db).items():
        changes = edit_log.diff(before[(entity_type, card)], values)
        edit_log.record(db, entity_type, card, "update", user_id, label=names[entity_type][card], changes=changes)
