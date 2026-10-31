"""Team settings on the Cài đặt pages. /settings/ai: each LLM provider's API key, base URL and model, and which
provider writes the scripts. An API key only ever goes in: responses carry its last four characters at most."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import crypto, llm
from .claude import ClaudeError
from .db import get_db
from .errors import ApiError
from .models import AppSetting, LlmProvider, Session, User
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
