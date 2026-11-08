"""Team settings on the Cài đặt pages. /settings/ai: each LLM provider's API key, base URL and model, and which
provider writes the scripts. An API key only ever goes in: responses carry its last four characters at most."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import (
    auto_photos,
    config,
    crypto,
    image_providers,
    image_style,
    llm,
    routes_videos,
    source_keys,
    tts,
    video_options,
)
from .claude import ClaudeError
from .db import get_db
from .errors import ApiError
from .models import AppSetting, LlmProvider, MusicTrack, Session, User
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/settings")

MAX_KEY_LENGTH = 500
MAX_URL_LENGTH = 500
MAX_MODEL_LENGTH = 200


class ProviderBody(BaseModel):
    base_url: str | None = None  # "" restores the default
    model: str | None = None  # "" restores the default
    api_key: str | None = None  # a new key; leave out to keep the saved one
    remove_key: bool = False


class ActiveBody(BaseModel):
    provider: str


class DefaultsBody(BaseModel):
    values: dict


class SourceBody(BaseModel):
    enabled: bool


class ImageProviderBody(BaseModel):
    provider: str


class ImageStyleBody(BaseModel):
    style: str | None


class SourceKeyBody(BaseModel):
    api_key: str  # "" removes the saved key


def _preset(provider_id: str) -> llm.Preset:
    preset = llm.BY_ID.get(provider_id)
    if preset is None:
        raise ApiError(404, "provider_not_found", "Không có nhà cung cấp này")
    return preset


def _provider(db: DbSession, preset: llm.Preset, row: LlmProvider | None, active: str) -> dict:
    target = llm.target(db, preset.id)
    saved_key = llm.stored_key(row)
    key_source = "saved" if saved_key else ("env" if target.key else None)
    updated_by = db.get(User, row.updated_by_id) if row and row.updated_by_id else None
    return {
        "id": preset.id,
        "name": preset.name,
        "kind": preset.kind,
        "needs_key": preset.needs_key,
        "key_source": key_source,
        "key_tail": row.key_tail if saved_key else None,
        # A key saved before the storage folder's key changed can no longer be read.
        "key_unreadable": bool(row and row.key_encrypted and not saved_key),
        "base_url": row.base_url if row else "",
        "default_base_url": preset.base_url,
        "model": row.model if row else "",
        "model_suggestions": list(preset.models),
        "effective_base_url": target.base_url,
        "effective_model": target.model,
        "problem": llm.problem(target),
        "active": preset.id == active,
        "updated_at": row.updated_at.isoformat() if row else None,
        "updated_by": updated_by.name if updated_by else None,
    }


def _payload(db: DbSession) -> dict:
    rows = {row.id: row for row in db.scalars(select(LlmProvider))}
    active = llm.active_id(db)
    return {
        "active": active,
        "providers": [_provider(db, preset, rows.get(preset.id), active) for preset in llm.PRESETS],
    }


def _clean_key(key: str) -> str:
    key = key.strip()
    if not key:
        raise invalid("Hãy dán API key")
    if len(key) > MAX_KEY_LENGTH or len(key.split()) > 1:
        raise invalid("API key không hợp lệ, hãy chép lại đúng một dòng key")
    return key


@router.get("/llm")
def get_llm(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _payload(db)


@router.patch("/llm/{provider_id}")
def update_provider(
    provider_id: str, body: ProviderBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    preset = _preset(provider_id)
    row = db.scalar(select(LlmProvider).where(LlmProvider.id == preset.id).with_for_update())
    if row is None:
        row = LlmProvider(id=preset.id, base_url="", model="")
        db.add(row)
    if body.base_url is not None:
        url = body.base_url.strip().rstrip("/")
        if len(url) > MAX_URL_LENGTH or (url and not llm.valid_base_url(url)):
            raise invalid("Base URL phải là một địa chỉ http:// hoặc https://, ví dụ https://api.openai.com/v1")
        row.base_url = url
    if body.model is not None:
        model = body.model.strip()
        if len(model) > MAX_MODEL_LENGTH or len(model.split()) > 1:
            raise invalid("Tên model không hợp lệ: một dòng, không có khoảng trắng")
        row.model = model
    if body.remove_key:
        row.key_encrypted = row.key_tail = None
    elif body.api_key is not None:
        key = _clean_key(body.api_key)
        row.key_encrypted, row.key_tail = crypto.encrypt(key), key[-llm.KEY_TAIL :]
    row.updated_by_id = me.user_id
    db.flush()
    if llm.active_id(db) == preset.id and (reason := llm.problem(llm.target(db, preset.id))):
        # The provider in use must stay usable: a script job would fail with this reason.
        db.rollback()
        raise invalid(f"{preset.name} đang được dùng để viết kịch bản. {reason}")
    db.commit()
    return _payload(db)


@router.put("/llm/active")
def set_active(body: ActiveBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    preset = _preset(body.provider)
    reason = llm.problem(llm.target(db, preset.id))
    if reason:
        raise invalid(reason)
    setting = db.get(AppSetting, llm.ACTIVE_KEY)
    if setting is None:
        db.add(AppSetting(key=llm.ACTIVE_KEY, value=preset.id, updated_by_id=me.user_id))
    else:
        setting.value, setting.updated_by_id = preset.id, me.user_id
    db.commit()
    return _payload(db)


@router.post("/llm/{provider_id}/models")
def list_models(provider_id: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Kiểm tra kết nối": lists the provider's models with the saved settings. It costs no tokens."""
    preset = _preset(provider_id)
    try:
        models = llm.list_models(llm.target(db, preset.id))
    except ClaudeError as err:
        raise ApiError(422, "provider_refused", err.message) from None
    return {"models": models}


# Kept for the "Tạo video" dialog and the video page: which provider and model would write a script now.
@router.get("/llm/active")
def get_active(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    target = llm.active_target(db)
    return {"provider": target.provider, "name": target.name, "model": target.model, "problem": llm.problem(target)}


# --- Cài đặt › Mặc định video ---


def _defaults_payload(db: DbSession, values: dict) -> dict:
    """The team defaults, with the default music's name and player link for the page ("music_track", read-only):
    None when there is none or the track was deleted from the library since (new videos then start silent)."""
    track = db.get(MusicTrack, values["music_track_id"]) if values.get("music_track_id") else None
    music = {"id": track.id, "name": track.name, "url": f"/api/music/{track.id}/audio.mp3"} if track else None
    return values | {"music_track": music}


@router.get("/video-defaults")
def get_video_defaults(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """What a new video starts with; existing videos keep their own copy."""
    return _defaults_payload(db, video_options.team_defaults(db))


def _check_track_in(db: DbSession, values: dict) -> None:
    """A well-formed default track id must name a track in the library (a malformed one is refused by
    video_options.clean)."""
    track_id = values.get("music_track_id")
    known = isinstance(track_id, int) and not isinstance(track_id, bool) and track_id >= 1
    if known and db.get(MusicTrack, track_id) is None:
        raise ApiError(404, "track_not_found", "Không tìm thấy bài nhạc (có thể đã bị xóa)")


@router.put("/video-defaults")
def put_video_defaults(
    body: DefaultsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    _check_track_in(db, body.values)
    try:
        saved = video_options.save_team_defaults(db, body.values, me.user_id)
    except video_options.OptionError as err:
        raise invalid(str(err)) from None
    db.commit()
    return _defaults_payload(db, saved)


# --- The signed-in member's own defaults: theirs once saved, the team's until then ---


def _mine_payload(db: DbSession, me: Session) -> dict:
    """The member's defaults for the page, with whose they are and whether they are their own yet."""
    user = db.get(User, me.user_id)
    return _defaults_payload(db, video_options.member_defaults(db, me.user_id)) | {
        "own": video_options.has_own_defaults(db, me.user_id),
        "owner": user.name if user else "",
    }


@router.get("/my-video-defaults")
def get_my_video_defaults(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """What the signed-in member's new videos start with."""
    return _mine_payload(db, me)


@router.put("/my-video-defaults")
def put_my_video_defaults(
    body: DefaultsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """Saves the member's own defaults: what they use now (the team's, the first time) with these values changed."""
    _check_track_in(db, body.values)
    try:
        video_options.save_member_defaults(db, me.user_id, body.values)
    except video_options.OptionError as err:
        raise invalid(str(err)) from None
    db.commit()
    return _mine_payload(db, me)


@router.delete("/my-video-defaults")
def delete_my_video_defaults(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Dùng mặc định nhóm": the member's new videos start with the team's defaults again."""
    video_options.forget_member_defaults(db, me.user_id)
    db.commit()
    return _mine_payload(db, me)


@router.get("/voices")
def get_voices(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The voices to choose from: ElevenLabs' and VieNeu's, each listed once its key is set, and the server's default
    one. A service that cannot list its voices is named in `problems` while the other's voices still come; with no
    voice at all, the reason is the error."""
    keys = {name: source_keys.get(db, name) for name in ("elevenlabs", "vieneu")}
    if not any(keys.values()):
        raise ApiError(
            422,
            "voices_unavailable",
            "Chưa có key ElevenLabs hay VieNeu nên chưa chọn được giọng đọc: nhập key ElevenLabs ở Cài đặt › "
            "Nguồn tư liệu, hoặc key VieNeu ở Cài đặt › Mô hình AI",
        )
    voices: list[dict] = []
    problems: list[str] = []
    for name, listing in (("elevenlabs", tts.list_voices), ("vieneu", tts.list_vieneu_voices)):
        if not keys[name]:
            if name == "elevenlabs":
                # The server's default voice is an ElevenLabs one, so say why it cannot be read.
                problems.append(tts.NO_KEY.format("chưa dùng được giọng ElevenLabs (cả giọng mặc định)"))
            continue
        try:
            voices += listing(keys[name])
        except tts.TtsError as err:
            problems.append(err.message)
    if not voices:
        raise ApiError(422, "voices_unavailable", problems[0])
    return {"default_id": config.voice_id(), "voices": voices, "problems": problems}


# --- Cài đặt › Nguồn tư liệu ---

SOURCE_KINDS = {"pixabay": "Ảnh và video", "pexels": "Ảnh và video", "openverse": "Ảnh (chỉ ảnh không cần ghi nguồn)"}
SOURCE_SIGNUP = {
    "pixabay": "https://pixabay.com/api/docs/",
    "pexels": "https://www.pexels.com/api/",
    "gemini": "https://aistudio.google.com/apikey",
    "cloudflare": "https://dash.cloudflare.com/profile/api-tokens",
    "elevenlabs": "https://elevenlabs.io/app/settings/api-keys",
    "vieneu": "https://www.vieneu.io/#/developer",
}


def _key(db: DbSession, name: str) -> dict:
    """What the page shows of a key: where it comes from and its last four characters, never the key itself."""
    key = source_keys.get(db, name)
    return {
        "origin": source_keys.origin(db, name),
        "hint": key[-4:] if len(key) >= 12 else "",
        "signup_url": SOURCE_SIGNUP[name],
    }


def _sources(db: DbSession) -> dict:
    off = routes_videos.stock_turned_off(db)
    return {
        "sources": [
            {
                "id": source,
                "label": routes_videos.STOCK_LABELS[source],
                "kinds": SOURCE_KINDS[source],
                "key": _key(db, source) if source in source_keys.ENV_NAMES else None,
                "configured": routes_videos.stock_configured(source, db),
                "enabled": source not in off,
            }
            for source in routes_videos.STOCK_SOURCES
        ],
        # Both AI image providers; the team's default (image_providers.default) makes AI photos unless a member
        # picks the other for one press. "ai_provider_saved": chosen on this page rather than worked out.
        "ai_provider": image_providers.default(db),
        "ai_provider_saved": image_providers.saved(db) is not None,
        # The style the image job adds to every scene's prompt (image_style.py).
        "ai_style": image_style.payload(db),
        # "Tự tìm ảnh sau khi viết kịch bản" (auto_photos.py), on unless the team turned it off.
        "auto_photos": auto_photos.enabled(db),
        "ai_images": {
            "configured": bool(source_keys.get(db, "gemini")),
            "model": config.image_gen_model(),
            "key": _key(db, "gemini"),
        },
        "ai_images_cloudflare": {
            "configured": bool(source_keys.get(db, "cloudflare") and config.image_gen_cf_account_id()),
            "model": config.image_gen_cf_model(),
            "account_id_set": bool(config.image_gen_cf_account_id()),
            "key": _key(db, "cloudflare"),
        },
        # Narration (ElevenLabs): the render job and the voice picker use this key.
        "voices": {"configured": bool(source_keys.get(db, "elevenlabs")), "key": _key(db, "elevenlabs")},
        # Narration (VieNeu), its key pasted on Cài đặt › Mô hình AI: voices whose id starts with "vieneu:".
        "vieneu": {"configured": bool(source_keys.get(db, "vieneu")), "key": _key(db, "vieneu")},
    }


@router.get("/image-providers")
def get_image_providers(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """For the arrow beside "Tạo ảnh AI" buttons: both providers, whether each is set up, and the default."""
    return image_providers.offered(db)


@router.put("/image-provider")
def set_image_provider(
    body: ImageProviderBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The team's default AI image provider ("Nguồn ảnh AI mặc định" on Cài đặt › Nguồn tư liệu)."""
    if body.provider not in image_providers.PROVIDERS:
        raise invalid("Nguồn ảnh AI không hợp lệ")
    image_providers.save(db, body.provider, me.user_id)
    db.commit()
    return _sources(db)


@router.put("/auto-photos")
def set_auto_photos(body: SourceBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    auto_photos.save(db, body.enabled, me.user_id)
    db.commit()
    return _sources(db)


@router.put("/image-style")
def set_image_style(
    body: ImageStyleBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Phong cách ảnh AI": None goes back to the default, an empty text adds nothing to the prompts."""
    try:
        image_style.save(db, body.style, me.user_id)
    except image_style.ImageStyleError as err:
        raise invalid(str(err)) from None
    db.commit()
    return _sources(db)


@router.get("/sources")
def get_sources(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _sources(db)


@router.put("/sources/{source}")
def set_source(
    source: str, body: SourceBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    if source not in routes_videos.STOCK_SOURCES:
        raise ApiError(404, "source_not_found", "Không có nguồn này")
    off = routes_videos.stock_turned_off(db) - {source} | (set() if body.enabled else {source})
    setting = db.get(AppSetting, routes_videos.STOCK_OFF_KEY)
    if setting is None:
        db.add(AppSetting(key=routes_videos.STOCK_OFF_KEY, value=sorted(off), updated_by_id=me.user_id))
    else:
        setting.value, setting.updated_by_id = sorted(off), me.user_id
    db.commit()
    return _sources(db)


@router.put("/sources/{name}/key")
def set_source_key(
    name: str, body: SourceKeyBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """Save a pasted key for Pixabay, Pexels, Gemini or Cloudflare (AI images); an empty key removes the saved one."""
    if name not in source_keys.ENV_NAMES:
        raise ApiError(404, "source_not_found", "Nguồn này không cần key")
    try:
        source_keys.save(db, name, body.api_key, me.user_id)
    except source_keys.SourceKeyError as err:
        raise invalid(str(err)) from None
    db.commit()
    return _sources(db)
