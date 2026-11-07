"""Scene narration with ElevenLabs (the "Adam" voice by default) or VieNeu, called only from the voice and render jobs.

A video's voice id says which service reads it: "vieneu:<VieNeu voice id>" is a VieNeu voice (its OpenAI-compatible
/v1/audio/speech), any other id an ElevenLabs one. Each scene's MP3 is stored with the signature of what it was made
from, so a re-render pays only for narration whose text, voice or model changed.
"""

import hashlib
import json
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from reels_render.errors import RenderError
from reels_render.ffmpeg import find_tools, run

from . import config

REQUEST_TIMEOUT = 120
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_VOICE_ID_LENGTH = 64  # videos.options["voice_id"], prefix included; video_options checks the same length

VIENEU_PREFIX = "vieneu:"
VIENEU_MODEL = "vieneu-v4"
VIENEU_ENGINE = "v4"


class TtsError(Exception):
    """`message` is shown to members, `detail` is diagnostic."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def spoken_text(voice_text: str) -> str:
    return " ".join(voice_text.split())


# The reading speed is a tempo factor applied with FFmpeg to the MP3 ElevenLabs returns (the "Tốc độ đọc" slider).
# ElevenLabs' own voice_settings.speed is not used: the default model, eleven_v3, ignores it.
MIN_SPEED, MAX_SPEED, SPEED_STEP = 0.7, 1.3, 0.05


def is_vieneu(voice_id: str | None) -> bool:
    return bool(voice_id) and voice_id.startswith(VIENEU_PREFIX)


def key_name(voice_id: str | None) -> str:
    """The source_keys name of the key that reads this voice (the server's default voice is an ElevenLabs one)."""
    return "vieneu" if is_vieneu(voice_id) else "elevenlabs"


def service_name(voice_id: str | None) -> str:
    return "VieNeu" if is_vieneu(voice_id) else "ElevenLabs"


def voice_signature(voice_text: str, voice_id: str | None = None, speed: float = 1.0) -> str:
    """What one narration MP3 is made from. The speed joins only when it is not 1, so narration made before
    speeds existed stays valid; it joins as "tempo:<factor>", so narration made at an old preset ("tempo:fast")
    or while the speed was left to ElevenLabs (and ignored by eleven_v3) is made again."""
    voice = voice_id or config.voice_id()
    data = [voice, VIENEU_MODEL if is_vieneu(voice) else config.voice_model(), spoken_text(voice_text)]
    if speed != 1.0:
        data.append(f"tempo:{speed:g}")
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


NO_KEY = "Chưa có key ElevenLabs nên {}: nhập key ở Cài đặt › Nguồn tư liệu"
NO_VIENEU_KEY = "Chưa có key VieNeu nên {}: nhập key ở Cài đặt › Mô hình AI"


def synthesize(voice_text: str, key: str, voice_id: str | None = None, speed: float = 1.0) -> bytes:
    """The narration as MP3 bytes, in the given voice (the server's default when None) and speed (a tempo
    factor applied here with FFmpeg). `key` is the key of the voice's service (key_name) as source_keys gives it:
    pasted on the settings pages, else the .env one."""
    voice = voice_id or config.voice_id()
    if is_vieneu(voice):
        return change_speed(_vieneu_speech(voice_text, key, voice.removeprefix(VIENEU_PREFIX)), speed)
    if not key:
        raise TtsError(NO_KEY.format("không tạo được lời đọc"))
    url = f"{config.elevenlabs_api_url()}/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
    payload = {"text": spoken_text(voice_text), "model_id": config.voice_model(), "language_code": "vi"}
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
    return change_speed(data, speed)


def _vieneu_speech(voice_text: str, key: str, voice: str) -> bytes:
    """VieNeu's MP3 for the text: its OpenAI-compatible endpoint answers with the audio bytes themselves."""
    if not key:
        raise TtsError(NO_VIENEU_KEY.format("không tạo được lời đọc"))
    payload = {"model": VIENEU_MODEL, "input": spoken_text(voice_text), "voice": voice, "response_format": "mp3"}
    request = urllib.request.Request(
        f"{config.vieneu_api_url()}/v1/audio/speech",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = response.read(MAX_AUDIO_BYTES + 1)
    except urllib.error.HTTPError as err:
        raise _vieneu_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    except OSError as err:
        raise TtsError("Không kết nối được VieNeu, kiểm tra mạng rồi thử lại", str(err)) from None
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise TtsError("VieNeu trả file lời đọc không dùng được, thử lại sau", f"{len(data)} bytes")
    return data


def _vieneu_error(status: int, body: str) -> TtsError:
    detail = f"HTTP {status}: {body}"
    lowered = body.lower()
    if status == 401:
        return TtsError("Key VieNeu không hợp lệ hoặc đã bị thu hồi: kiểm tra lại ở Cài đặt › Mô hình AI", detail)
    if status == 429:
        if "trial" in lowered:
            return TtsError("Key VieNeu dùng thử đã hết lượt gọi trong ngày, thử lại sau 0 giờ", detail)
        return TtsError("VieNeu đang giới hạn lượt gọi, thử lại sau", detail)
    if status == 402 or "credit" in lowered or "quota" in lowered or "balance" in lowered:
        return TtsError("Tài khoản VieNeu đã hết lượt (credit), cần nạp thêm", detail)
    if status == 403:
        return TtsError("Tài khoản VieNeu chưa có gói API đang hoạt động", detail)
    if status == 400 and "voice" in lowered:
        return TtsError("VieNeu không có giọng đã chọn, hãy chọn giọng khác", detail)
    if status >= 500:
        return TtsError(f"VieNeu đang lỗi (HTTP {status}), thử lại sau", detail)
    return TtsError("VieNeu từ chối tạo lời đọc", detail)


def change_speed(data: bytes, speed: float) -> bytes:
    """The MP3 sped up or slowed down by the factor, keeping the pitch (FFmpeg atempo); unchanged at 1."""
    if speed == 1.0:
        return data
    with tempfile.TemporaryDirectory() as folder:
        source, output = Path(folder) / "voice.mp3", Path(folder) / "voice-tempo.mp3"
        source.write_bytes(data)
        try:
            run(
                [
                    find_tools().ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-filter:a",
                    f"atempo={speed:g}",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    str(output),
                ],
                "FFmpeg không đổi được tốc độ lời đọc",
            )
        except RenderError as err:
            raise TtsError("Không đổi được tốc độ lời đọc, thử lại sau", str(err)) from None
        return output.read_bytes()


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
                "service": "elevenlabs",
            }
        )
    voices.sort(key=lambda voice: voice["name"].lower())
    _voices_cache[cache_key] = (time.monotonic(), voices)
    return voices


def list_vieneu_voices(key: str) -> list[dict]:
    """VieNeu's v4 voices for the voice picker, each id prefixed with "vieneu:". The catalogue itself needs no key,
    but its voices are offered only once a key is set, since reading them needs one; the key is sent along so the
    account's own voices may come too. Kept for 10 minutes like ElevenLabs' list."""
    if not key:
        raise TtsError(NO_VIENEU_KEY.format("chưa chọn được giọng VieNeu"))
    url = f"{config.vieneu_api_url()}/v1/voices?engine={VIENEU_ENGINE}"
    cache_key = (url, hashlib.sha256(key.encode()).hexdigest())
    cached = _voices_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < VOICES_CACHE_SECONDS:
        return cached[1]
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=VOICES_TIMEOUT) as response:
            data = json.loads(response.read(2_000_000))
    except urllib.error.HTTPError as err:
        raise _vieneu_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    except (OSError, ValueError) as err:
        raise TtsError("Không lấy được danh sách giọng VieNeu, thử lại sau", str(err)) from None
    voices = []
    for item in data.get("voices", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            continue
        # A voice of another engine is refused when read (HTTP 400), so it is not offered.
        if item.get("engine") not in (None, VIENEU_ENGINE):
            continue
        voice_id = VIENEU_PREFIX + item["id"]
        if len(voice_id) > MAX_VOICE_ID_LENGTH:
            continue
        voices.append(
            {
                "id": voice_id,
                "name": str(item.get("name") or item["id"]),
                "description": str(item.get("description") or ""),
                "preview_url": None,
                "service": "vieneu",
            }
        )
    voices.sort(key=lambda voice: voice["name"].lower())
    _voices_cache[cache_key] = (time.monotonic(), voices)
    return voices
