"""The team's shared style for AI photos, added to every scene's prompt by the image job.

Scene prompts (written by the script, editable on each card) describe only what is in the photo; this text says how
every photo looks, so the scenes of a video match and the look can change without touching a script. It is app data,
edited on Cài đặt › Nguồn tư liệu; an empty style adds nothing.
"""

from sqlalchemy.orm import Session as DbSession

from .models import AppSetting

SETTING_KEY = "image_style"
MAX_LENGTH = 500
DEFAULT = (
    "Realistic photo, natural soft light, warm Vietnamese home setting, vertical 9:16 composition, "
    "subject in the centre, no text, no letters, no watermark, no logo"
)


class ImageStyleError(ValueError):
    """The message is shown to members."""


def _saved(db: DbSession) -> str | None:
    setting = db.get(AppSetting, SETTING_KEY)
    return setting.value if setting and isinstance(setting.value, str) else None


def get(db: DbSession) -> str:
    saved = _saved(db)
    return DEFAULT if saved is None else saved


def save(db: DbSession, style: str | None, user_id: int) -> None:
    """The team's style; None goes back to the default, "" adds nothing to the prompts."""
    if style is not None:
        style = " ".join(style.split())
        if len(style) > MAX_LENGTH:
            raise ImageStyleError(f"Phong cách ảnh quá dài (tối đa {MAX_LENGTH} ký tự)")
    setting = db.get(AppSetting, SETTING_KEY)
    if style is None:
        if setting is not None:
            db.delete(setting)
        return
    if setting is None:
        db.add(AppSetting(key=SETTING_KEY, value=style, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = style, user_id


def payload(db: DbSession) -> dict:
    return {"value": get(db), "default": DEFAULT, "custom": _saved(db) is not None}


def styled(prompt: str, style: str) -> str:
    """The scene's prompt followed by the style: "<what is in the photo>. <how every photo looks>"."""
    prompt, style = prompt.strip().rstrip("."), style.strip()
    return f"{prompt}. {style}" if style else prompt
