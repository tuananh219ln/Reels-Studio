"""Scene narration with ElevenLabs (the "Adam" voice by default), called only from the render job.

Each scene's MP3 is stored with the signature of what it was made from, so a re-render pays only for
narration whose text, voice or model changed.
"""

import hashlib
import json
import urllib.error
import urllib.request

from . import config

REQUEST_TIMEOUT = 120
MAX_AUDIO_BYTES = 20 * 1024 * 1024


class TtsError(Exception):
    """`message` is shown to members, `detail` is diagnostic."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def spoken_text(voice_text: str) -> str:
    return " ".join(voice_text.split())


def voice_signature(voice_text: str) -> str:
    data = [config.voice_id(), config.voice_model(), spoken_text(voice_text)]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def synthesize(voice_text: str) -> bytes:
    """The narration as MP3 bytes."""
    key = config.elevenlabs_key()
    if not key:
        raise TtsError("Chưa cấu hình ELEVENLABS_API_KEY nên không tạo được lời đọc")
    url = f"{config.elevenlabs_api_url()}/v1/text-to-speech/{config.voice_id()}?output_format=mp3_44100_128"
    body = json.dumps({
        "text": spoken_text(voice_text),
        "model_id": config.voice_model(),
        "language_code": "vi",
    }).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg",
    })
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = response.read(MAX_AUDIO_BYTES + 1)
    except urllib.error.HTTPError as err:
        raise _http_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    # URLError, timeouts, connection resets and SSL errors are all OSError subclasses.
    except OSError as err:
        raise TtsError("Không kết nối được ElevenLabs, kiểm tra mạng rồi thử lại", str(err)) from None
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise TtsError("ElevenLabs trả file lời đọc không dùng được, thử lại sau", f"{len(data)} bytes")
    return data


def _http_error(status: int, body: str) -> TtsError:
    detail = f"HTTP {status}: {body}"
    if "quota" in body.lower() or status == 402:
        return TtsError("Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm", detail)
    if status == 401:
        return TtsError("Key ElevenLabs (ELEVENLABS_API_KEY) không hợp lệ", detail)
    if status == 404:
        return TtsError("ElevenLabs không có giọng hoặc model đã cấu hình (ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL)",
                        detail)
    if status == 429:
        return TtsError("ElevenLabs đang giới hạn lượt gọi, thử lại sau", detail)
    if status >= 500:
        return TtsError(f"ElevenLabs đang lỗi (HTTP {status}), thử lại sau", detail)
    return TtsError("ElevenLabs từ chối tạo lời đọc", detail)
