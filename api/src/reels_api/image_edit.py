""" "Sửa ảnh": a scene's photo changed by AI, from its card, through the image_edit job.

Two tabs, three engines:

- "Xóa vùng": a member draws boxes over what should go (a logo, a watermark, a stray object) and the boxes are filled
  in from what is around them, by LaMa on the worker itself (`lama`, free; the ONNX model at LAMA_MODEL_PATH, baked
  into the worker image) or by Cloudflare's inpainting model (`cloudflare`, on the team's Cloudflare token). Only a
  square around the boxes is sent through the model and pasted back with a soft edge, so the rest of the photo keeps
  its full sharpness.
- "Sửa theo mô tả": a member asks in words ("làm nền sáng hơn") and Gemini edits the whole photo (`gemini`, paid).

Called only from the image_edit job, which stores the result like any photo (it still goes through the upload
checks) and keeps the photo from before the first edit, so "Khôi phục ảnh gốc" can bring it back.
"""

import base64
import binascii
import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

from . import config
from .imagegen import ImageGenError, _cf_messages, _cf_out_of_neurons, gemini_image
from .uploads import MAX_IMAGE_BYTES

ENGINES = ("lama", "cloudflare", "gemini")
LABELS = {"lama": "Xóa nhanh (LaMa)", "cloudflare": "Cloudflare", "gemini": "Gemini"}
ERASERS = ("lama", "cloudflare")
MAX_BOXES = 10
# A box narrower or shorter than this share of the photo is a slip of the mouse, not a choice.
MIN_BOX = 0.004
MAX_PROMPT = 500
# LaMa's ONNX export takes exactly this square; Stable Diffusion 1.5 inpainting works best at it too.
MODEL_SIZE = 512
JPEG_QUALITY = 92
REQUEST_TIMEOUT = 120
# What Cloudflare is asked to paint in a box when the member gives no words: the surroundings, without marks.
CF_FILL_PROMPT = "seamless continuation of the surrounding background, natural texture, clean surface"
CF_NEGATIVE_PROMPT = "text, letters, words, logo, watermark, signature, frame, border"
CF_STEPS = 20  # the model's own default and maximum
# Gemini is sent the photo at most this long on its longer side: enough to edit, without paying for pixels.
GEMINI_MAX_SIDE = 1536

Box = list[float]  # [x, y, width, height], fractions of the photo


def clean_boxes(raw: object) -> list[Box]:
    """The boxes a member drew, checked and kept inside the photo; ValueError carries the message members see."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("Hãy khoanh ít nhất một vùng trên ảnh")
    if len(raw) > MAX_BOXES:
        raise ValueError(f"Khoanh tối đa {MAX_BOXES} vùng mỗi lần")
    boxes = []
    for item in raw:
        if (
            not isinstance(item, list | tuple)
            or len(item) != 4
            or not all(isinstance(value, int | float) and not isinstance(value, bool) for value in item)
        ):
            raise ValueError("Vùng khoanh không hợp lệ")
        x, y, width, height = (float(value) for value in item)
        left, top = max(0.0, x), max(0.0, y)
        right, bottom = min(1.0, x + width), min(1.0, y + height)
        if right - left < MIN_BOX or bottom - top < MIN_BOX:
            raise ValueError("Vùng khoanh quá nhỏ hoặc nằm ngoài ảnh")
        boxes.append([round(left, 4), round(top, 4), round(right - left, 4), round(bottom - top, 4)])
    return boxes


def clean_prompt(raw: object, required: bool) -> str:
    text = raw.strip() if isinstance(raw, str) else ""
    if required and not text:
        raise ValueError("Hãy viết điều cần sửa trên ảnh")
    if len(text) > MAX_PROMPT:
        raise ValueError(f"Mô tả tối đa {MAX_PROMPT} ký tự")
    return text


def edit(data: bytes, engine: str, boxes: list[Box] | None, prompt: str, key: str) -> bytes:
    """The edited photo as image bytes; `key` is the engine's (Cloudflare's or Gemini's), unused by LaMa."""
    image = _open(data)
    if engine == "gemini":
        return _gemini_edit(image, prompt, key)
    if engine == "cloudflare":
        return erase(image, boxes or [], lambda patch, mask: _cloudflare_fill(patch, mask, prompt, key))
    if engine == "lama":
        return erase(image, boxes or [], _lama_fill)
    raise ImageGenError(f"Cách sửa ảnh không hỗ trợ: {engine}")


def _open(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            # Turned the way it is shown (a phone photo's EXIF), so the boxes drawn over it land where they were drawn.
            return ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageGenError("Không đọc được ảnh của cảnh này") from None


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


# --- Xóa vùng ---

Fill = Callable[[Image.Image, Image.Image], Image.Image]


def erase(image: Image.Image, boxes: list[Box], fill: Fill) -> bytes:
    """The photo with its boxes filled in by `fill`, which gets a square patch around them and its mask (white where
    to fill) and answers the patch filled in, at any size. Everything outside the boxes stays as it was."""
    if not boxes:
        raise ImageGenError("Hãy khoanh ít nhất một vùng trên ảnh")
    width, height = image.size
    # A little past the box, so the soft edge of a logo (its shadow, its antialiasing) goes with it.
    grow = max(3, round(min(width, height) * 0.008))
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    for x, y, box_width, box_height in boxes:
        draw.rectangle(
            (
                max(0, round(x * width) - grow),
                max(0, round(y * height) - grow),
                min(width, round((x + box_width) * width) + grow) - 1,
                min(height, round((y + box_height) * height) + grow) - 1,
            ),
            fill=255,
        )
    region = patch_region(image.size, mask.getbbox())
    patch, patch_mask = image.crop(region), mask.crop(region)
    filled = fill(patch, patch_mask).convert("RGB").resize(patch.size, Image.Resampling.LANCZOS)
    # Feathered inside the grown box only, so the photo just outside it is never touched.
    soft = patch_mask.filter(ImageFilter.GaussianBlur(grow / 2))
    result = image.copy()
    result.paste(Image.composite(filled, patch, soft), region[:2])
    return _jpeg(result)


def patch_region(size: tuple[int, int], bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """A square around `bbox` with room on every side for the model to see what surrounds it, kept inside the photo
    (narrower than square only when the photo itself is)."""
    width, height = size
    left, top, right, bottom = bbox
    margin = max(48, round(max(right - left, bottom - top) * 0.6))
    side = min(max(right - left, bottom - top) + 2 * margin, max(width, height))
    centre_x, centre_y = (left + right) / 2, (top + bottom) / 2

    def span(centre: float, limit: int) -> tuple[int, int]:
        length = min(side, limit)
        start = round(centre - length / 2)
        start = max(0, min(start, limit - length))
        return start, start + length

    x0, x1 = span(centre_x, width)
    y0, y1 = span(centre_y, height)
    return x0, y0, x1, y1


_lama: tuple[str, object] | None = None


def _lama_session():
    """The ONNX session, loaded once per worker (about 200 MB; a second photo then takes only the inference)."""
    global _lama
    path = config.lama_model_path()
    if not path or not Path(path).is_file():
        raise ImageGenError(
            "Máy chủ chưa có model LaMa để xóa vùng (LAMA_MODEL_PATH): hãy chọn Cloudflare hoặc báo người quản trị",
            f"LAMA_MODEL_PATH={path!r}",
        )
    if _lama is None or _lama[0] != path:
        try:
            import onnxruntime  # only the worker image has it; the api never loads it
        except ImportError:
            raise ImageGenError(
                "Máy chủ chưa cài phần xóa vùng (onnxruntime): hãy chọn Cloudflare hoặc báo người quản trị"
            ) from None
        options = onnxruntime.SessionOptions()
        options.log_severity_level = 3
        _lama = (path, onnxruntime.InferenceSession(path, options, providers=["CPUExecutionProvider"]))
    return _lama[1]


def _lama_fill(patch: Image.Image, mask: Image.Image) -> Image.Image:
    import numpy  # installed with onnxruntime, in the worker image only

    session = _lama_session()
    square = (MODEL_SIZE, MODEL_SIZE)
    pixels = numpy.asarray(patch.resize(square, Image.Resampling.LANCZOS), dtype=numpy.float32) / 255.0
    hole = (numpy.asarray(mask.resize(square, Image.Resampling.NEAREST), dtype=numpy.float32) > 127).astype(
        numpy.float32
    )
    inputs = session.get_inputs()
    feeds = {
        inputs[0].name: pixels.transpose(2, 0, 1)[None],
        inputs[1].name: hole[None, None],
    }
    try:
        output = session.run(None, feeds)[0][0]
    except Exception as err:  # onnxruntime raises its own types; any fails only this photo
        raise ImageGenError("LaMa không xóa được vùng này, thử lại hoặc chọn Cloudflare", repr(err)) from None
    # The model answers 0–255, not 0–1.
    return Image.fromarray(numpy.clip(output.transpose(1, 2, 0), 0, 255).astype(numpy.uint8), "RGB")


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _cloudflare_fill(patch: Image.Image, mask: Image.Image, prompt: str, key: str) -> Image.Image:
    if not key:
        raise ImageGenError("Chưa có API token Cloudflare: nhập token ở Cài đặt › Nguồn tư liệu")
    account = config.image_gen_cf_account_id()
    if not account:
        raise ImageGenError("Chưa cấu hình IMAGE_GEN_CF_ACCOUNT_ID (Account ID của Cloudflare) trong .env của server")
    square = (MODEL_SIZE, MODEL_SIZE)
    body = {
        "prompt": prompt or CF_FILL_PROMPT,
        "negative_prompt": CF_NEGATIVE_PROMPT,
        # The model takes each picture as the bytes of an image file.
        "image": list(_png(patch.resize(square, Image.Resampling.LANCZOS))),
        "mask": list(_png(mask.resize(square, Image.Resampling.NEAREST))),
        "width": MODEL_SIZE,
        "height": MODEL_SIZE,
        "num_steps": CF_STEPS,
        "strength": 1,
    }
    url = f"{config.image_gen_cf_api_url()}/accounts/{account}/ai/run/{config.image_inpaint_cf_model()}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            kind = response.headers.get("Content-Type", "")
            raw = response.read(MAX_IMAGE_BYTES * 2 + 1)
    except urllib.error.HTTPError as err:
        raise _cf_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    except OSError as err:
        raise ImageGenError("Không kết nối được Cloudflare, kiểm tra mạng rồi thử lại", str(err)) from None
    if len(raw) > MAX_IMAGE_BYTES * 2:
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau", f"{len(raw)} bytes")
    # The model answers the PNG itself; a JSON answer is an error, or the image in base64 on some accounts.
    if not kind.startswith("application/json"):
        return _image_or_error(raw, "Cloudflare")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau") from None
    if not isinstance(payload, dict) or payload.get("success") is False:
        messages = _cf_messages(payload)
        raise _cf_refused(messages, json.dumps(payload)[:500])
    result = payload.get("result")
    data = result.get("image") if isinstance(result, dict) else None
    if not data:
        raise ImageGenError("Cloudflare không trả ảnh, thử lại sau", json.dumps(payload)[:500])
    try:
        return _image_or_error(base64.b64decode(data, validate=True), "Cloudflare")
    except (binascii.Error, ValueError):
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau") from None


def _image_or_error(data: bytes, service: str) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageGenError(f"{service} trả ảnh không đọc được, thử lại sau") from None


def _cf_refused(messages: str, detail: str) -> ImageGenError:
    if _cf_out_of_neurons(messages):
        return _cf_limit(detail)
    return ImageGenError("Cloudflare từ chối sửa ảnh này", f"{messages} | {detail}" if messages else detail)


def _cf_limit(detail: str) -> ImageGenError:
    return ImageGenError(
        "Cloudflare đã hết lượt miễn phí hôm nay (mở lại lúc 7 giờ sáng giờ Việt Nam): hãy chọn Xóa nhanh (LaMa)",
        detail,
    )


def _cf_error(status: int, body: str) -> ImageGenError:
    detail = f"HTTP {status}: {body}"
    try:
        messages = _cf_messages(json.loads(body))
    except ValueError:
        messages = ""
    if status in (401, 403):
        return ImageGenError("API token Cloudflare không hợp lệ: kiểm tra lại ở Cài đặt › Nguồn tư liệu", detail)
    if status == 429 or _cf_out_of_neurons(messages):
        return _cf_limit(detail)
    if status >= 500:
        return ImageGenError(f"Cloudflare đang lỗi (HTTP {status}), thử lại sau", detail)
    return _cf_refused(messages, detail)


# --- Sửa theo mô tả ---


def _gemini_edit(image: Image.Image, prompt: str, key: str) -> bytes:
    if not prompt:
        raise ImageGenError("Hãy viết điều cần sửa trên ảnh")
    if not key:
        raise ImageGenError("Chưa có key Gemini nên không sửa được ảnh: nhập key ở Cài đặt › Nguồn tư liệu")
    sent = image.copy()
    sent.thumbnail((GEMINI_MAX_SIDE, GEMINI_MAX_SIDE), Image.Resampling.LANCZOS)
    parts = [
        {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(_jpeg(sent)).decode()}},
        # The member's own words, as they wrote them: Gemini keeps the rest of the photo by itself.
        {"text": prompt},
    ]
    return _jpeg(_image_or_error(gemini_image(parts, key), "Gemini"))


def check() -> None:
    """The worker image's build check: one box erased by LaMa on a drawn photo, through `edit` as the job calls it."""
    photo = Image.new("RGB", (720, 1280), (190, 120, 60))
    ImageDraw.Draw(photo).rectangle((300, 600, 420, 660), fill=(255, 255, 255))
    data = edit(_jpeg(photo), "lama", [[0.4, 0.46, 0.2, 0.06]], "", "")
    with Image.open(io.BytesIO(data)) as result:
        assert result.size == (720, 1280), result.size
        # The white mark is gone: its middle is close to the photo around it again.
        red, green, blue = result.convert("RGB").getpixel((360, 630))
        assert abs(red - 190) + abs(green - 120) + abs(blue - 60) < 90, (red, green, blue)
    print("LaMa ok")


if __name__ == "__main__":
    check()
