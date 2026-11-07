"""Text, sticker and photo layers over a scene ("Chữ & sticker" in the studio, "Ảnh món" on a scene of a
"Video xuyên suốt"), each saved on its own like the scene fields.

The picture of a layer is drawn by the render core (reels_render.layers), so the studio's phone shows exactly what
the MP4 overlays. A photo layer shows its scene's own photo, so every way of choosing a scene's photo chooses it.
"""

import io
import math
import unicodedata

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from reels_render.layers import ANIMATIONS, PHOTO_SHAPES, SIZES, STICKERS, TEXT_STYLES, Layer, render_layer
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH

from .db import get_db
from .errors import ApiError
from .models import Scene, SceneLayer, Session
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .videos import ensure_unlocked, is_backdrop, lock_scene, photo_layer, video_payload

router = APIRouter(prefix="/api/layers")

MAX_TEXT_LENGTH = 200
MAX_START = 60
MIN_SECONDS, MAX_SECONDS = 0.3, 60
FIELDS = ("kind", "text", "sticker", "start", "seconds", "x", "y", "size", "style", "animation")
KINDS = ("text", "sticker", "photo")
KIND_ERROR = 'Loại lớp phải là "text", "sticker" hoặc "photo"'


class LayerBody(BaseModel):
    kind: object = None
    text: object = None
    sticker: object = None
    start: object = None
    seconds: object = None
    x: object = None
    y: object = None
    size: object = None
    style: object = None
    animation: object = None


class NewLayerBody(LayerBody):
    scene_id: int


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def as_layer(row: SceneLayer, image=None) -> Layer:
    return Layer(
        kind=row.kind,
        text=row.text,
        sticker=row.sticker,
        start=row.start,
        seconds=row.seconds,
        x=row.x,
        y=row.y,
        size=row.size,
        style=row.style,
        animation=row.animation,
        image=image,
    )


def _number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise invalid(f"{label} phải là số")
    if not low <= value <= high:
        raise invalid(f"{label} phải từ {low:g} đến {high:g}")
    return value


def _preset(value: object, presets: dict, label: str) -> str:
    if not isinstance(value, str) or value not in presets:
        raise invalid(f"{label} không hợp lệ: {value!r}")
    return value


def _apply(row: SceneLayer, body: LayerBody) -> None:
    """Checks and sets every field the body names, then that the layer can be drawn."""
    # The kind first: what a style means depends on it.
    for field in sorted(body.model_fields_set & set(FIELDS), key=lambda name: name != "kind"):
        value = getattr(body, field)
        if field == "kind":
            if value not in KINDS:
                raise invalid(KIND_ERROR)
            row.kind = value
        elif field == "text":
            if not isinstance(value, str):
                raise invalid("Chữ của lớp phải là chuỗi")
            value = unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip()
            if len(value) > MAX_TEXT_LENGTH:
                raise invalid(f"Chữ của lớp dài quá {MAX_TEXT_LENGTH} ký tự")
            row.text = value
        elif field == "sticker":
            # Empty on a text layer; a sticker layer without one is refused below.
            row.sticker = "" if value == "" else _preset(value, STICKERS, "Sticker")
        elif field == "start":
            row.start = round(_number(value, "Giây bắt đầu", 0, MAX_START), 2)
        elif field == "seconds":
            row.seconds = round(_number(value, "Số giây", MIN_SECONDS, MAX_SECONDS), 2)
        elif field in ("x", "y"):
            limit = FRAME_WIDTH if field == "x" else FRAME_HEIGHT
            setattr(row, field, round(_number(value, "Vị trí", 0, limit)))
        elif field == "size":
            row.size = _preset(value, SIZES, "Cỡ")
        elif field == "style":
            if row.kind == "photo":
                row.style = _preset(value, PHOTO_SHAPES, "Khung ảnh")
            else:
                row.style = _preset(value, TEXT_STYLES, "Kiểu chữ")
        elif field == "animation":
            row.animation = _preset(value, ANIMATIONS, "Hiệu ứng vào")
    if row.kind == "text" and not row.text:
        raise invalid("Lớp chữ cần có chữ")
    if row.kind == "sticker" and row.sticker not in STICKERS:
        raise invalid("Sticker không hợp lệ: hãy chọn một sticker")
    if row.kind == "photo":
        # Drawn from the scene's photo, which may be chosen later; the render checks it is there.
        return
    try:
        render_layer(as_layer(row))
    except ValueError as err:
        raise invalid(f"Chữ của lớp không vừa: {err}") from None


def _layer(db: DbSession, layer_id: int) -> tuple:
    """The layer's scene and video locked, then the layer re-read: a teammate may have removed it meanwhile."""
    scene_id = db.scalar(select(SceneLayer.scene_id).where(SceneLayer.id == layer_id))
    if scene_id is None:
        raise ApiError(404, "layer_not_found", "Lớp này đã bị xoá")
    video, scene = lock_scene(db, scene_id)
    row = db.get(SceneLayer, layer_id)
    if row is None:
        raise ApiError(404, "layer_not_found", "Lớp này đã bị xoá")
    return video, scene, row


def _saved(db: DbSession, video) -> dict:
    db.commit()
    return video_payload(db, video)


@router.post("", status_code=201)
def add_layer(body: NewLayerBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A new layer over the scene, on top of its others; unnamed fields take the defaults (2 s, centred, fading in)."""
    video, scene = lock_scene(db, body.scene_id)
    ensure_unlocked(db, video)
    if scene.is_title:
        raise invalid("Cảnh tiêu đề không có lớp chữ hay sticker: nó là ảnh bìa của video")
    last = db.scalar(select(func.max(SceneLayer.position)).where(SceneLayer.scene_id == scene.id))
    defaults = Layer(kind="text")
    photo = body.kind == "photo"
    if photo:
        if not is_backdrop(video):
            raise invalid("Ảnh món chỉ dùng cho Video xuyên suốt: đổi Kiểu video trước")
        if any(layer.kind == "photo" for layer in scene.layers):
            raise invalid("Cảnh này đã có ảnh món")
        # Left and right by turns among the scenes with a photo, counted up to this one.
        before = db.scalar(
            select(func.count(SceneLayer.id))
            .join(Scene, Scene.id == SceneLayer.scene_id)
            .where(Scene.video_id == video.id, Scene.position < scene.position, SceneLayer.kind == "photo")
        )
        defaults = as_layer(photo_layer(before or 0))
    row = SceneLayer(
        scene_id=scene.id,
        position=(last or 0) + 1,
        kind="",
        text="",
        sticker="",
        start=defaults.start,
        seconds=defaults.seconds,
        x=defaults.x,
        y=defaults.y,
        size=defaults.size,
        style=defaults.style,
        animation=defaults.animation,
    )
    if "kind" not in body.model_fields_set:
        raise invalid(KIND_ERROR)
    _apply(row, body)
    db.add(row)
    return _saved(db, video)


@router.patch("/{layer_id}")
def patch_layer(
    layer_id: int, body: LayerBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video, _, row = _layer(db, layer_id)
    ensure_unlocked(db, video)
    if "kind" in body.model_fields_set and body.kind != row.kind:
        raise invalid("Không đổi được loại lớp: hãy xoá lớp rồi thêm lớp mới")
    _apply(row, body)
    return _saved(db, video)


@router.delete("/{layer_id}")
def delete_layer(layer_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video, _, row = _layer(db, layer_id)
    ensure_unlocked(db, video)
    db.delete(row)
    return _saved(db, video)


@router.get("/stickers/{name}.png")
def sticker_image(name: str, me: Session = Depends(current_member)) -> Response:
    """A sticker at its small size, for the studio's list to pick one from."""
    if name not in STICKERS:
        raise ApiError(404, "sticker_not_found", "Không có sticker này")
    buffer = io.BytesIO()
    render_layer(Layer(kind="sticker", sticker=name, size="small")).save(buffer, "PNG")
    return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{layer_id}/image.png")
def layer_image(
    layer_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    """The layer's picture exactly as the render overlays it (transparent around it)."""
    row = db.get(SceneLayer, layer_id)
    scene = db.get(Scene, row.scene_id) if row is not None else None
    if scene is None:
        raise ApiError(404, "layer_not_found", "Lớp này đã bị xoá")
    image = None
    if row.kind == "photo":
        if not scene.image_key or not storage.exists(scene.image_key):
            raise ApiError(404, "photo_not_found", "Cảnh chưa có ảnh cho ảnh món")
        image = storage.path(scene.image_key)
    buffer = io.BytesIO()
    try:
        picture = render_layer(as_layer(row, image))
    except ValueError as err:
        raise ApiError(422, "photo_unreadable", f"Không vẽ được ảnh món: {err}") from None
    picture.save(buffer, "PNG")
    return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
