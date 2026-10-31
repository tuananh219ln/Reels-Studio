"""AI photos for scenes that have none, by Gemini image generation via Google AI Studio.

Called only from the image job. The returned bytes still go through the upload checks
(uploads.image_extension) before they are stored, and the scene records the model as its
source (`ai:<model>`), so a generated photo is told apart from an upload or a stock photo.
"""

import base64
import binascii
import json
import urllib.error
import urllib.request

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


def generate_image(prompt: str) -> bytes:
    """One photo for the prompt, as raw image bytes (format not yet checked)."""
    key = config.image_gen_key()
    if not key:
        raise ImageGenError("Chưa cấu hình IMAGE_GEN_API_KEY nên không tạo được ảnh AI", fatal=True)
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
        return ImageGenError("Key Gemini (IMAGE_GEN_API_KEY) không hợp lệ", detail, fatal=True)
    if status == 404:
        return ImageGenError("Gemini không có model đã cấu hình (IMAGE_GEN_MODEL)", detail, fatal=True)
    if status >= 500:
        return ImageGenError(f"Gemini đang lỗi (HTTP {status}), thử lại sau", detail)
    return ImageGenError("Gemini từ chối tạo ảnh cho cảnh này", detail)
