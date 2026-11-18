"""How much of each AI service's allowance is used, for the cards on Cài đặt › Nguồn tư liệu.

Each service tells a different amount:
- ElevenLabs answers it exactly: the plan's characters used and allowed, and when they reset (GET
  /v1/user/subscription; a key limited to some permissions needs "User: Read").
- Cloudflare Workers AI gives 10,000 free neurons a day, reset at 00:00 UTC. Today's neurons are read from its GraphQL
  Analytics API, which needs the token to also have "Account Analytics: Read"; without it the card shows the photos
  the app itself asked for today, which misses any other use of the same account.
- Gemini (Google AI Studio) has no API for the quota left or the money spent, so the card shows the requests the app
  sent today (photos, photo edits, narration) and links to AI Studio's own usage page. Its daily limits reset at
  midnight Pacific time.

The app's own count is one `ai_service_calls` row per request, recorded before the request is sent (it counts against
the quota even when it fails). What the services answer is kept a few minutes, so opening the page again does not call
them each time; "Làm mới" asks again.
"""

import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from . import config, source_keys
from .models import AiServiceCall

log = logging.getLogger(__name__)

SERVICES = ("gemini", "cloudflare")
KINDS = ("image", "edit", "voice")
KEEP_DAYS = 35
CF_FREE_NEURONS = 10_000
CACHE_SECONDS = 300
REQUEST_TIMEOUT = 15
PACIFIC = ZoneInfo("America/Los_Angeles")
GEMINI_USAGE_URL = "https://aistudio.google.com/usage"
CF_USAGE_URL = "https://dash.cloudflare.com/?to=/:account/ai/workers-ai"
ELEVENLABS_USAGE_URL = "https://elevenlabs.io/app/subscription"

# Today's neurons on the account (aiInferenceAdaptiveGroups.sum.totalNeurons, by UTC day).
CF_QUERY = """
query ($accountTag: string!, $date: Date!) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      aiInferenceAdaptiveGroups(limit: 1, filter: {date_geq: $date}) { sum { totalNeurons } }
    }
  }
}
"""

_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_cache_lock = threading.Lock()


class UsageError(Exception):
    """The message is shown to members."""


def record(db: DbSession, service: str, kind: str) -> None:
    """One request about to be sent; the caller commits. Rows past KEEP_DAYS go at the same time."""
    db.add(AiServiceCall(service=service, kind=kind))
    db.execute(delete(AiServiceCall).where(AiServiceCall.created_at < func.now() - timedelta(days=KEEP_DAYS)))


def calls_since(db: DbSession, service: str, since: datetime) -> dict[str, int]:
    rows = db.execute(
        select(AiServiceCall.kind, func.count())
        .where(AiServiceCall.service == service, AiServiceCall.created_at >= since)
        .group_by(AiServiceCall.kind)
    ).all()
    counts = dict.fromkeys(KINDS, 0)
    counts.update({kind: count for kind, count in rows})
    return counts


def utc_day_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def pacific_day_start(now: datetime) -> datetime:
    return now.astimezone(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)


def _next_day(start: datetime) -> datetime:
    """The next midnight in `start`'s own zone: aware datetimes add wall-clock time, so a Pacific day that is 23 or 25
    hours long when the clocks change still ends at midnight."""
    return start + timedelta(days=1)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _cached(service: str, key: str, fresh: bool, read) -> dict:
    """`read()`'s answer for this key, kept CACHE_SECONDS; an error is kept too, so a broken key is not asked often."""
    slot = (service, hashlib.sha256(key.encode()).hexdigest())
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(slot)
    if hit and not fresh and hit[0] > now:
        return hit[1]
    try:
        value = {"ok": True, **read()}
    except UsageError as err:
        value = {"ok": False, "error": str(err)}
    with _cache_lock:
        _cache[slot] = (now + CACHE_SECONDS, value)
    return value


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _request(request: urllib.request.Request, service: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            status, raw = response.status, response.read(200_000)
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read(4000)
    except OSError as err:  # URLError, timeouts, resets and SSL errors
        log.info("%s usage: %s", service, err)
        raise UsageError(f"Không kết nối được {service} để đọc hạn mức, thử lại sau") from None
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


# --- ElevenLabs ---


def _elevenlabs(key: str) -> dict:
    request = urllib.request.Request(f"{config.elevenlabs_api_url()}/v1/user/subscription", headers={"xi-api-key": key})
    status, body = _request(request, "ElevenLabs")
    detail = body.get("detail") if isinstance(body, dict) else None
    reason = detail.get("status") if isinstance(detail, dict) else ""
    if status == 401 and reason == "missing_permissions":
        raise UsageError("Key ElevenLabs chưa có quyền User › Read nên không đọc được hạn mức: tạo key có quyền này")
    if status in (401, 403):
        raise UsageError("Key ElevenLabs không hợp lệ nên không đọc được hạn mức")
    if status != 200 or not isinstance(body, dict):
        raise UsageError(f"ElevenLabs không trả hạn mức (HTTP {status}), thử lại sau")
    try:
        used, limit = int(body.get("character_count") or 0), int(body.get("character_limit") or 0)
    except (TypeError, ValueError):
        raise UsageError("ElevenLabs trả hạn mức không đọc được") from None
    reset = body.get("next_character_count_reset_unix")
    return {
        "tier": str(body.get("tier") or ""),
        "status": str(body.get("status") or ""),
        "characters_used": used,
        "characters_limit": limit,
        "resets_at": _iso(datetime.fromtimestamp(reset, UTC)) if isinstance(reset, int | float) and reset else None,
    }


def elevenlabs(db: DbSession, fresh: bool = False) -> dict:
    key = source_keys.get(db, "elevenlabs")
    if not key:
        return {"configured": False, "usage_url": ELEVENLABS_USAGE_URL}
    return {
        "configured": True,
        "usage_url": ELEVENLABS_USAGE_URL,
        **_cached("elevenlabs", key, fresh, lambda: _elevenlabs(key)),
    }


# --- Cloudflare ---


def _cloudflare_neurons(key: str, account: str, day: str) -> dict:
    body = json.dumps({"query": CF_QUERY, "variables": {"accountTag": account, "date": day}}).encode()
    request = urllib.request.Request(
        f"{config.image_gen_cf_api_url()}/graphql",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    status, answer = _request(request, "Cloudflare")
    errors = answer.get("errors") if isinstance(answer, dict) else None
    if status in (401, 403) or errors:
        messages = "; ".join(str(e.get("message", "")) for e in errors or [] if isinstance(e, dict))
        log.info("Cloudflare usage refused: HTTP %s %s", status, messages[:300])
        raise UsageError(
            "Token Cloudflare chưa có quyền Account Analytics › Read nên chưa đọc được số neurons: số dưới đây là"
            " app tự đếm"
        )
    if status != 200 or not isinstance(answer, dict):
        raise UsageError(f"Cloudflare không trả số neurons (HTTP {status}): số dưới đây là app tự đếm")
    try:
        accounts = answer["data"]["viewer"]["accounts"]
        groups = accounts[0]["aiInferenceAdaptiveGroups"] if accounts else []
        neurons = float(groups[0]["sum"]["totalNeurons"] or 0) if groups else 0.0
    except (KeyError, IndexError, TypeError, ValueError):
        raise UsageError("Cloudflare trả số neurons không đọc được: số dưới đây là app tự đếm") from None
    return {"neurons_used": round(neurons, 1)}


def cloudflare(db: DbSession, fresh: bool = False, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    start = utc_day_start(now)
    key, account = source_keys.get(db, "cloudflare"), config.image_gen_cf_account_id()
    result = {
        "configured": bool(key and account),
        "neurons_limit": CF_FREE_NEURONS,
        "calls_today": calls_since(db, "cloudflare", start),
        "resets_at": _iso(_next_day(start)),
        "usage_url": CF_USAGE_URL,
    }
    if not result["configured"]:
        return result
    day = start.date().isoformat()
    return result | _cached(
        "cloudflare", f"{account}:{day}:{key}", fresh, lambda: _cloudflare_neurons(key, account, day)
    )


# --- Gemini ---


def gemini(db: DbSession, now: datetime | None = None) -> dict:
    """Only the app's own count: Google has no API for the quota left."""
    now = now or datetime.now(UTC)
    start = pacific_day_start(now)
    return {
        "configured": bool(source_keys.get(db, "gemini")),
        "calls_today": calls_since(db, "gemini", start),
        "resets_at": _iso(_next_day(start)),
        "usage_url": GEMINI_USAGE_URL,
    }


def payload(db: DbSession, fresh: bool = False) -> dict:
    return {"elevenlabs": elevenlabs(db, fresh), "cloudflare": cloudflare(db, fresh), "gemini": gemini(db)}
