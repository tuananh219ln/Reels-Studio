"""The sample picture of each PC Shopee title preset, for the picker on a video's Thiết lập (docs/decisions/2026-11-27-title-presets.md)."""

import io
from functools import lru_cache

from fastapi import APIRouter, Depends, Response

from reels_render.pc_text import PRESETS
from reels_render.tiers import TitleTiers, render_title

from .errors import ApiError
from .models import Session
from .sessions import current_member

router = APIRouter(prefix="/api/title-presets")

SAMPLE = TitleTiers("BLACK FRIDAY", "GIÁ RẺ BẤT NGỜ", "MÁY TÍNH ĐỒ HOẠ", "")
WIDTH = 360  # px: the picker's tile; the title is drawn at 1080 and scaled down


@lru_cache(maxsize=len(PRESETS))
def sample_png(style: str) -> bytes:
    from PIL import Image

    picture = render_title(SAMPLE, style)
    picture = picture.resize((WIDTH, max(1, round(picture.height * WIDTH / picture.width))), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    picture.save(out, format="PNG")
    return out.getvalue()


@router.get("/{style}.png")
def sample(style: str, me: Session = Depends(current_member)) -> Response:
    if style not in PRESETS:
        raise ApiError(404, "not_found", "Không có kiểu chữ này")
    return Response(sample_png(style), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
