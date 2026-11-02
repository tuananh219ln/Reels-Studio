"""AI photos for scenes that have none, from one of two providers: Gemini image generation via Google AI Studio
(the default) or Cloudflare Workers AI (FLUX.1 schnell), dispatched by `provider` (image_providers: the team's default or the one chosen for a press).

Gemini is asked for the 9:16 frame directly. Cloudflare's FLUX.1 schnell ignores width/height and always answers
a 1024x1024 square, so that branch cuts the centre to 9:16 here before returning.

Called only from the image job. The returned bytes still go through the upload checks
(uploads.image_extension) before they are stored, and the scene records the model as its
source (`ai:<model>`), so a generated photo is told apart from an upload or a stock photo.
"""

import base64
import binascii
import io
import json
import urllib.error
import urllib.request

from PIL import Image, UnidentifiedImageError

from . import config
from .uploads import MAX_IMAGE_BYTES

REQUEST_TIMEOUT = 120


class ImageGenError(Exception):
    """`message` is shown to members, `detail` is diagnostic.

    `fatal` marks a provider-wide failure (missing or invalid key, quota, unknown model):
    the image job stops at once instead of failing every remaining scene one by one.
    """

    def __init__(self, message: str, detail: str = "", fatal: bool = False):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.fatal = fatal


def generate_image(prompt: str, key: str, provider: str = "gemini") -> bytes:
    """One photo for the prompt, as raw image bytes (format not yet checked); `key` is the provider's, from
    source_keys."""
    if provider == "cloudflare":
        return _generate_cloudflare(prompt, key)
    return _generate_gemini(prompt, key)


def _generate_gemini(prompt: str, key: str) -> bytes:
    if not key:
        raise ImageGenError(
            "Chưa có key Gemini nên không tạo được ảnh AI: nhập key ở Cài đặt › Nguồn tư liệu", fatal=True
        )
    url = f"{config.image_gen_api_url()}/v1beta/models/{config.image_gen_model()}:generateContent"
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            # Scenes are frames of a vertical reel: ask for the 9:16 frame explicitly instead
            # of cropping whatever comes back.
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}},
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.HTTPError as err:
        raise _http_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    # URLError, timeouts, connection resets and SSL errors are all OSError subclasses.
    except OSError as err:
        raise ImageGenError("Không kết nối được Gemini, kiểm tra mạng rồi thử lại", str(err)) from None
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageGenError("Gemini trả kết quả quá lớn, thử lại sau", f"{len(raw)} bytes")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise ImageGenError("Gemini trả kết quả không đọc được, thử lại sau") from None
    feedback = payload.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise ImageGenError(
            "Gemini từ chối tạo ảnh cho cảnh này (an toàn nội dung)", f"blockReason={feedback['blockReason']}"
        )
    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            data = (part.get("inlineData") or {}).get("data")
            if data:
                try:
                    return base64.b64decode(data)
                except (binascii.Error, ValueError):
                    raise ImageGenError("Gemini trả ảnh không đọc được, thử lại sau") from None
    raise ImageGenError("Gemini không trả ảnh cho cảnh này, thử lại sau", json.dumps(payload)[:500])


def _http_error(status: int, body: str) -> ImageGenError:
    detail = f"HTTP {status}: {body}"
    lowered = body.lower()
    if status == 429 or "quota" in lowered or "resource_exhausted" in lowered:
        return ImageGenError("Tài khoản Gemini đã hết hạn mức (quota), cần đợi hoặc nâng gói", detail, fatal=True)
    if status in (401, 403):
        return ImageGenError("Key Gemini không hợp lệ: kiểm tra lại ở Cài đặt › Nguồn tư liệu", detail, fatal=True)
    if status == 404:
        return ImageGenError("Gemini không có model đã cấu hình (IMAGE_GEN_MODEL)", detail, fatal=True)
    if status >= 500:
        return ImageGenError(f"Gemini đang lỗi (HTTP {status}), thử lại sau", detail)
    return ImageGenError("Gemini từ chối tạo ảnh cho cảnh này", detail)


# --- Cloudflare Workers AI ---

CF_STEPS = 4  # FLUX.1 schnell's own default and maximum
FRAME_RATIO = 9 / 16
JPEG_QUALITY = 90


def _generate_cloudflare(prompt: str, key: str) -> bytes:
    if not key:
        raise ImageGenError(
            "Chưa có API token Cloudflare nên không tạo được ảnh AI: nhập token ở Cài đặt › Nguồn tư liệu", fatal=True
        )
    account = config.image_gen_cf_account_id()
    if not account:
        raise ImageGenError(
            "Chưa cấu hình IMAGE_GEN_CF_ACCOUNT_ID (Account ID của Cloudflare) trong .env của server", fatal=True
        )
    url = f"{config.image_gen_cf_api_url()}/accounts/{account}/ai/run/{config.image_gen_cf_model()}"
    # No width/height: FLUX.1 schnell on Cloudflare ignores them and answers a square.
    request = urllib.request.Request(
        url,
        data=json.dumps({"prompt": prompt, "steps": CF_STEPS}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read(MAX_IMAGE_BYTES * 2 + 1)
    except urllib.error.HTTPError as err:
        raise _cf_http_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    # URLError, timeouts, connection resets and SSL errors are all OSError subclasses.
    except OSError as err:
        raise ImageGenError("Không kết nối được Cloudflare, kiểm tra mạng rồi thử lại", str(err)) from None
    if len(raw) > MAX_IMAGE_BYTES * 2:  # base64 inside JSON: about 4/3 of the image
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau", f"{len(raw)} bytes")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau") from None
    if not isinstance(payload, dict):
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau")
    if payload.get("success") is False:
        raise _cf_refused(_cf_messages(payload), json.dumps(payload)[:500])
    data = (payload.get("result") or {}).get("image") if isinstance(payload.get("result"), dict) else None
    if not data:
        raise ImageGenError("Cloudflare không trả ảnh cho cảnh này, thử lại sau", json.dumps(payload)[:500])
    try:
        image = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau") from None
    return _vertical(image)


def _cf_messages(payload: object) -> str:
    errors = payload.get("errors") if isinstance(payload, dict) else None
    return "; ".join(str(item.get("message", "")) for item in errors or [] if isinstance(item, dict))


def _cf_out_of_neurons(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ("neuron", "quota", "limit"))


def _cf_refused(messages: str, detail: str) -> ImageGenError:
    if _cf_out_of_neurons(messages):
        return _cf_limit(detail)
    return ImageGenError("Cloudflare từ chối tạo ảnh cho cảnh này", f"{messages} | {detail}" if messages else detail)


def _cf_limit(detail: str) -> ImageGenError:
    return ImageGenError(
        "Cloudflare đã hết lượt tạo ảnh miễn phí hôm nay (mở lại lúc 7 giờ sáng giờ Việt Nam): chọn Gemini ở mũi tên"
        " cạnh nút tạo ảnh để tạo tiếp",
        detail,
        fatal=True,
    )


def _cf_http_error(status: int, body: str) -> ImageGenError:
    detail = f"HTTP {status}: {body}"
    try:
        messages = _cf_messages(json.loads(body))
    except ValueError:
        messages = ""
    if status in (401, 403):
        return ImageGenError(
            "API token Cloudflare không hợp lệ: kiểm tra lại ở Cài đặt › Nguồn tư liệu", detail, fatal=True
        )
    if status == 429 or _cf_out_of_neurons(messages):
        return _cf_limit(detail)
    if status >= 500:
        return ImageGenError(f"Cloudflare đang lỗi (HTTP {status}), thử lại sau", detail)
    return _cf_refused(messages, detail)


def _vertical(data: bytes) -> bytes:
    """The centre of the photo cut to 9:16 and saved as JPEG; a photo already 9:16 (within a pixel) is kept."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            width, height = source.size
            target = round(height * FRAME_RATIO)
            if abs(width - target) <= 1:
                return data
            if width > target:
                left = (width - target) // 2
                box = (left, 0, left + target, height)
            else:
                cut = round(width / FRAME_RATIO)
                top = (height - cut) // 2
                box = (0, top, width, top + cut)
            buffer = io.BytesIO()
            source.crop(box).convert("RGB").save(buffer, "JPEG", quality=JPEG_QUALITY)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageGenError("Cloudflare trả ảnh không đọc được, thử lại sau") from None
