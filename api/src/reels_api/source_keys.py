"""API keys of the stock libraries (Pixabay, Pexels, Unsplash), both AI image providers (Gemini, Cloudflare Workers AI) and
ElevenLabs, VieNeu and Google Cloud Text-to-Speech (narration), all pasted on Cài đặt › AI và nguồn tư liệu.

A key saved there is stored encrypted (crypto) and wins over the server's .env; with none saved, the .env key is
used, so a server set up before this page keeps working. A saved key is never sent back to the browser.

The three narration services (TTS_SERVICES) may have more keys (api_keys): the team's backup keys, tried in order
after the main key above once it fails. `chain` gives them in the order a narration tries them, and `mark` keeps why a
key last failed so its row on the settings page says so; the main key alone (`get`) still makes AI photos, edits
photos and writes a sample's words down.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import config, crypto
from .models import ApiKey, AppSetting

SETTING_KEY = "source_keys"  # app_settings value: {name: encrypted key}
ERRORS_KEY = "source_key_errors"  # app_settings value: {service: {"main"|"env": {"error", "at"}}}
ENV_NAMES = {
    "pixabay": "PIXABAY_API_KEY",
    "pexels": "PEXELS_API_KEY",
    "unsplash": "UNSPLASH_ACCESS_KEY",
    "gemini": "IMAGE_GEN_API_KEY",
    "cloudflare": "IMAGE_GEN_CF_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "vieneu": "VIENEU_API_KEY",
    "google_tts": "GOOGLE_TTS_API_KEY",
}
MAX_KEY_LENGTH = 300
TTS_SERVICES = ("elevenlabs", "gemini", "vieneu", "google_tts")
MAX_LABEL_LENGTH = 40
MAX_KEYS = 10  # backup keys per service
MAX_ERROR_LENGTH = 300
SHORT_KEY = 12  # a shorter key shows no characters at all


class SourceKeyError(ValueError):
    """The message is shown to members."""


def _stored(db: DbSession) -> dict:
    setting = db.get(AppSetting, SETTING_KEY)
    return dict(setting.value) if setting and isinstance(setting.value, dict) else {}


def _saved(db: DbSession, name: str) -> str | None:
    """The saved key; None when none is saved or the storage folder's key cannot read it."""
    encrypted = _stored(db).get(name)
    if not isinstance(encrypted, str) or not encrypted:
        return None
    try:
        return crypto.decrypt(encrypted)
    except crypto.CannotDecrypt:
        return None


def get(db: DbSession, name: str) -> str:
    """The key in use; "" for a name that takes no key."""
    if name not in ENV_NAMES:
        return ""
    return _saved(db, name) or config.read_env(ENV_NAMES[name])


def origin(db: DbSession, name: str) -> str | None:
    """Where the key in use comes from: "saved" (this page), "unreadable" (saved, but must be pasted again),
    "env" (the server's .env) or None (no key)."""
    if name in _stored(db):
        return "saved" if _saved(db, name) else "unreadable"
    return "env" if config.read_env(ENV_NAMES[name]) else None


def checked(key: str) -> str:
    """The pasted key without spaces around it; one string of at most MAX_KEY_LENGTH characters."""
    key = key.strip()
    if len(key) > MAX_KEY_LENGTH or len(key.split()) > 1:
        raise SourceKeyError("Key không hợp lệ: dán đúng một chuỗi key, không có khoảng trắng")
    return key


def hint(key: str) -> str:
    """The last four characters a page or a log may show; none for a short key."""
    return key[-4:] if len(key) >= SHORT_KEY else ""


def save(db: DbSession, name: str, key: str, user_id: int) -> None:
    """Save a pasted key, or remove the saved one when `key` is empty (the .env key, if any, applies again)."""
    key = checked(key)
    stored = _stored(db)
    if key:
        stored[name] = crypto.encrypt(key)
    else:
        stored.pop(name, None)
    setting = db.get(AppSetting, SETTING_KEY)
    if setting is None:
        db.add(AppSetting(key=SETTING_KEY, value=stored, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = stored, user_id
    if name in TTS_SERVICES:
        _set_main_error(db, name, "main", None)  # a new key starts with a clean slate


# --- Backup narration keys of the team ---


@dataclass(frozen=True)
class KeyRef:
    """One key a narration may try. `origin`: "main" (the team's key above), "shared" (a backup key) or "env" (the
    server's). `id` is the api_keys row, None for the main and .env keys."""

    key: str = field(repr=False)
    label: str
    hint: str
    origin: str
    id: int | None = None

    @property
    def shown(self) -> str:
        """How logs and messages name the key: its label and last characters, never the key."""
        return f"{self.label} …{self.hint}" if self.hint else self.label


def rows(db: DbSession, service: str) -> list[ApiKey]:
    """The team's backup keys of one service, in the order they are tried."""
    return list(db.scalars(select(ApiKey).where(ApiKey.service == service).order_by(ApiKey.position, ApiKey.id)))


def chain(db: DbSession, service: str) -> list[KeyRef]:
    """Every key a narration tries, in order: the team's main key (or the .env one when none is saved, as before), the
    backups, then the .env key if not tried yet. A key that cannot be read (the storage folder's key changed) is left
    out; the same key twice is tried once."""
    if service not in TTS_SERVICES:
        return []
    found: list[KeyRef] = []
    saved = _saved(db, service)
    env = config.read_env(ENV_NAMES[service])
    if saved:
        found.append(KeyRef(saved, "Key chính", hint(saved), "main"))
    elif env:
        found.append(KeyRef(env, "Key trong .env", hint(env), "env"))
    for row in rows(db, service):
        try:
            key = crypto.decrypt(row.key_encrypted)
        except crypto.CannotDecrypt:
            continue
        found.append(KeyRef(key, row.label, row.tail, "shared", row.id))
    if env and saved:
        found.append(KeyRef(env, "Key trong .env", hint(env), "env"))
    unique: list[KeyRef] = []
    for ref in found:
        if all(ref.key != seen.key for seen in unique):
            unique.append(ref)
    return unique


def _errors(db: DbSession) -> dict:
    setting = db.get(AppSetting, ERRORS_KEY)
    return dict(setting.value) if setting and isinstance(setting.value, dict) else {}


def _set_main_error(db: DbSession, service: str, origin: str, error: dict | None) -> None:
    errors = _errors(db)
    service_errors = dict(errors.get(service) or {})
    if error is None and origin not in service_errors:
        return
    if error is None:
        service_errors.pop(origin)
    else:
        service_errors[origin] = error
    errors[service] = service_errors
    setting = db.get(AppSetting, ERRORS_KEY)
    if setting is None:
        db.add(AppSetting(key=ERRORS_KEY, value=errors))
    else:
        setting.value = errors


def mark(db: DbSession, service: str, ref: KeyRef, error: str | None) -> None:
    """Keep why `ref` just failed (its wrong or spent key), or forget an earlier failure once it reads again; the
    caller commits. Nothing is written when nothing changes, so a working key costs no write per scene."""
    if ref.id is not None:
        row = db.get(ApiKey, ref.id)
        if row is None or (error is None and row.error is None):
            return
        row.error = error[:MAX_ERROR_LENGTH] if error else None
        row.error_at = datetime.now(UTC) if error else None
        return
    value = {"error": error[:MAX_ERROR_LENGTH], "at": datetime.now(UTC).isoformat()} if error else None
    _set_main_error(db, service, ref.origin, value)


def main_error(db: DbSession, service: str) -> dict | None:
    """The last failure of the key the settings page shows as the main one: the saved key, else the .env key."""
    origin = "main" if service in _stored(db) else "env"
    error = (_errors(db).get(service) or {}).get(origin)
    return error if isinstance(error, dict) else None


def readable(row: ApiKey) -> bool:
    try:
        crypto.decrypt(row.key_encrypted)
    except crypto.CannotDecrypt:
        return False
    return True


def add(db: DbSession, service: str, label: str, key: str, by: int) -> ApiKey:
    """A new key at the end of the team's backups; the caller commits."""
    if service not in TTS_SERVICES:
        raise SourceKeyError("Dịch vụ này chỉ có một key")
    key = checked(key)
    if not key:
        raise SourceKeyError("Hãy dán key")
    existing = rows(db, service)
    if len(existing) >= MAX_KEYS:
        raise SourceKeyError(f"Đã đủ {MAX_KEYS} key cho dịch vụ này: xoá bớt key cũ trước")
    label = label.strip() or f"Key dự phòng {len(existing) + 1}"
    if len(label) > MAX_LABEL_LENGTH:
        raise SourceKeyError(f"Tên key tối đa {MAX_LABEL_LENGTH} ký tự")
    last = db.scalar(select(func.max(ApiKey.position)).where(ApiKey.service == service))
    row = ApiKey(
        service=service,
        label=label,
        key_encrypted=crypto.encrypt(key),
        tail=hint(key),
        position=(last or 0) + 1,
        created_by_id=by,
    )
    db.add(row)
    db.flush()
    return row


def rename(row: ApiKey, label: str) -> None:
    label = label.strip()
    if not label or len(label) > MAX_LABEL_LENGTH:
        raise SourceKeyError(f"Tên key phải có từ 1 đến {MAX_LABEL_LENGTH} ký tự")
    row.label = label


def move(db: DbSession, row: ApiKey, step: int) -> None:
    """One place earlier (step -1) or later (+1); nothing at either end."""
    keys = rows(db, row.service)
    index = next(i for i, other in enumerate(keys) if other.id == row.id)
    target = index + (1 if step > 0 else -1)
    if not 0 <= target < len(keys):
        return
    keys[index], keys[target] = keys[target], keys[index]
    for position, other in enumerate(keys, start=1):
        other.position = position
