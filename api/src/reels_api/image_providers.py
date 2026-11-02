"""Which AI image provider makes a photo: the team's default from Cài đặt › Nguồn tư liệu, or one chosen for a press.

The default is, in order: the provider saved on that page; IMAGE_GEN_PROVIDER from the server's .env when it is
set (servers set up before the page keep working); Cloudflare when it is set up (free, about 57 photos a day);
Gemini when only it is; Cloudflare otherwise, whose job then says what is missing. Running out of one provider
never switches to the other by itself: Gemini costs money, so a member chooses it for that press.
"""

from sqlalchemy.orm import Session as DbSession

from . import config, source_keys
from .models import AppSetting

PROVIDERS = ("cloudflare", "gemini")
LABELS = {"cloudflare": "Cloudflare", "gemini": "Gemini"}
SETTING_KEY = "image_gen_provider"


def configured(db: DbSession, provider: str) -> bool:
    if provider == "cloudflare":
        return bool(source_keys.get(db, "cloudflare") and config.image_gen_cf_account_id())
    return bool(source_keys.get(db, "gemini"))


def saved(db: DbSession) -> str | None:
    setting = db.get(AppSetting, SETTING_KEY)
    return setting.value if setting and setting.value in PROVIDERS else None


def default(db: DbSession) -> str:
    chosen = saved(db)
    if chosen:
        return chosen
    from_env = config.read_env("IMAGE_GEN_PROVIDER").strip().lower()
    if from_env:
        return "cloudflare" if from_env == "cloudflare" else "gemini"
    if configured(db, "cloudflare"):
        return "cloudflare"
    return "gemini" if configured(db, "gemini") else "cloudflare"


def save(db: DbSession, provider: str, user_id: int) -> None:
    if provider not in PROVIDERS:
        raise ValueError(provider)
    setting = db.get(AppSetting, SETTING_KEY)
    if setting is None:
        db.add(AppSetting(key=SETTING_KEY, value=provider, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = provider, user_id


def choose(db: DbSession, requested: str | None) -> str:
    """The provider for one press: the one asked for, else the team's default."""
    if requested is None or requested == "":
        return default(db)
    if requested not in PROVIDERS:
        raise ValueError(requested)
    return requested


def offered(db: DbSession) -> dict:
    """For the buttons' arrow menus and the settings page."""
    return {
        "default": default(db),
        "providers": [
            {"id": provider, "label": LABELS[provider], "configured": configured(db, provider)}
            for provider in PROVIDERS
        ],
    }
