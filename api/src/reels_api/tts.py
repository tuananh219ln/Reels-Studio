"""Scene narration with ElevenLabs (the "Adam" voice by default), called only from the render job.

Each scene's MP3 is stored with the signature of what it was made from, so a re-render pays only for
narration whose text, voice or model changed.
"""

import hashlib
import json
import time
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


# ElevenLabs voice_settings.speed for each speed preset (video_options.SPEEDS).
SPEEDS = {"slow": 0.9, "normal": 1.0, "fast": 1.1}


def voice_signature(voice_text: str, voice_id: str | None = None, speed: str = "normal") -> str:
    """What one narration MP3 is made from. The speed joins only when it is not the normal one, so narration
    made before speeds existed stays valid."""
    data = [voice_id or config.voice_id(), config.voice_model(), spoken_text(voice_text)]
    if speed != "normal":
        data.append(speed)
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


NO_KEY = "Chưa có key ElevenLabs nên {}: nhập key ở Cài đặt › Nguồn tư liệu"


def synthesize(voice_text: str, key: str, voice_id: str | None = None, speed: str = "normal") -> bytes:
    """The narration as MP3 bytes, in the given voice (the server's default when None) and speed. `key` is the
    ElevenLabs key in use (source_keys: pasted on Cài đặt › Nguồn tư liệu, else the .env one)."""
    if not key:
        raise TtsError(NO_KEY.format("không tạo được lời đọc"))
    voice = voice_id or config.voice_id()
    url = f"{config.elevenlabs_api_url()}/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
    payload: dict = {"text": spoken_text(voice_text), "model_id": config.voice_model(), "language_code": "vi"}
    if speed != "normal":
        payload["voice_settings"] = {"speed": SPEEDS[speed]}
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
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
        return TtsError("Key ElevenLabs không hợp lệ: kiểm tra lại ở Cài đặt › Nguồn tư liệu", detail)
    if status == 404:
        return TtsError(
            "ElevenLabs không có giọng hoặc model đã cấu hình (ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL)", detail
        )
    if status == 429:
        return TtsError("ElevenLabs đang giới hạn lượt gọi, thử lại sau", detail)
    if status >= 500:
        return TtsError(f"ElevenLabs đang lỗi (HTTP {status}), thử lại sau", detail)
    return TtsError("ElevenLabs từ chối tạo lời đọc", detail)


VOICES_TIMEOUT = 15
VOICES_CACHE_SECONDS = 600
_voices_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def list_voices(key: str) -> list[dict]:
    """The account's ElevenLabs voices for the voice picker: id, name, a short description and a sample URL.
    Listing costs no characters; the answer is kept for 10 minutes per key, so a newly pasted key lists at once."""
    if not key:
        raise TtsError(NO_KEY.format("chưa chọn được giọng đọc"))
    url = f"{config.elevenlabs_api_url()}/v1/voices"
    cache_key = (url, hashlib.sha256(key.encode()).hexdigest())
    cached = _voices_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < VOICES_CACHE_SECONDS:
        return cached[1]
    request = urllib.request.Request(url, headers={"xi-api-key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=VOICES_TIMEOUT) as response:
            data = json.loads(response.read(2_000_000))
    except urllib.error.HTTPError as err:
        raise _http_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    except (OSError, ValueError) as err:
        raise TtsError("Không lấy được danh sách giọng ElevenLabs, thử lại sau", str(err)) from None
    voices = []
    for item in data.get("voices", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not item.get("voice_id"):
            continue
        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
        description = ", ".join(str(labels[name]) for name in ("gender", "age", "accent") if labels.get(name))
        voices.append(
            {
                "id": str(item["voice_id"]),
                "name": str(item.get("name") or item["voice_id"]),
                "description": description,
                "preview_url": item.get("preview_url") or None,
            }
        )
    voices.sort(key=lambda voice: voice["name"].lower())
    _voices_cache[cache_key] = (time.monotonic(), voices)
    return voices
