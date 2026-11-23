"""Scene narration with ElevenLabs (the "Adam" voice by default), VieNeu or Gemini, called only from the voice and
render jobs.

A video's voice id says which service reads it: "vieneu:<VieNeu voice id>" is a VieNeu voice (its OpenAI-compatible
/v1/audio/speech), "gemini:<voice>" a Gemini TTS one (the Google AI Studio key that makes AI photos, its
/v1beta/interactions), any other id an ElevenLabs one. Each scene's MP3 is stored with the signature of what it was made
from, so a re-render pays only for narration whose text, voice or model changed.
"""

import base64
import binascii
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

GEMINI_PREFIX = "gemini:"
GEMINI_MODEL = "gemini-3.8-flash-tts"
GEMINI_RETRIES = 3  # a per-minute limit is waited out this many times before the job fails
GEMINI_RETRY_SECONDS = 20
# Gemini's 30 prebuilt voices speak any language it is given (Vietnamese included), picked by name; the word is
# Google's own description of the voice (ai.google.dev/gemini-api/docs/speech-generation#voices), in Vietnamese.
GEMINI_VOICES = {
    "Achernar": "Mềm",
    "Achird": "Thân thiện",
    "Algenib": "Khàn",
    "Algieba": "Mượt",
    "Alnilam": "Chắc",
    "Aoede": "Nhẹ nhàng",
    "Autonoe": "Sáng",
    "Callirrhoe": "Thoải mái",
    "Charon": "Rõ thông tin",
    "Despina": "Mượt",
    "Enceladus": "Hơi thở",
    "Erinome": "Rõ",
    "Fenrir": "Hào hứng",
    "Gacrux": "Chững chạc",
    "Iapetus": "Rõ",
    "Kore": "Chắc",
    "Laomedeia": "Tươi vui",
    "Leda": "Trẻ trung",
    "Orus": "Chắc",
    "Puck": "Tươi vui",
    "Pulcherrima": "Thẳng",
    "Rasalgethi": "Rõ thông tin",
    "Sadachbia": "Sôi nổi",
    "Sadaltager": "Hiểu biết",
    "Schedar": "Đều",
    "Sulafat": "Ấm",
    "Umbriel": "Thoải mái",
    "Vindemiatrix": "Dịu",
    "Zephyr": "Sáng",
    "Zubenelgenubi": "Tự nhiên",
}


class TtsError(Exception):
    """`message` is shown to members, `detail` is diagnostic. `key_fault`: the key itself cannot read (wrong or revoked,
    not allowed, its quota ran out), so another key of the same service may still; a busy or broken service, a
    network failure or a missing voice is not the key's fault and fails at once."""

    def __init__(self, message: str, detail: str = "", key_fault: bool = False):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.key_fault = key_fault


SERVICE_NAMES = {"elevenlabs": "ElevenLabs", "gemini": "Gemini", "vieneu": "VieNeu"}


def all_keys_failed(service: str, count: int) -> str:
    """The reason a narration fails once every one of the service's `count` keys was wrong or out of quota."""
    name = SERVICE_NAMES.get(service, service)
    return (
        f"Đã thử hết {count} key {name} và key nào cũng lỗi hoặc hết hạn mức: xem lỗi của từng key ở "
        "Cài đặt › AI và nguồn tư liệu, thêm key mới, hoặc chọn giọng dịch vụ khác cho video này"
    )


def spoken_text(voice_text: str) -> str:
    return " ".join(voice_text.split())


# The reading speed is a tempo factor applied with FFmpeg to the MP3 ElevenLabs returns (the "Tốc độ đọc" slider).
# ElevenLabs' own voice_settings.speed is not used: the default model, eleven_v3, ignores it.
MIN_SPEED, MAX_SPEED, SPEED_STEP = 0.7, 1.5, 0.05  # 1.5 for the fast comment-reading pages (2026-11-15)


def is_vieneu(voice_id: str | None) -> bool:
    return bool(voice_id) and voice_id.startswith(VIENEU_PREFIX)


def is_gemini(voice_id: str | None) -> bool:
    return bool(voice_id) and voice_id.startswith(GEMINI_PREFIX)


def key_name(voice_id: str | None) -> str:
    """The source_keys name of the key that reads this voice (the server's default voice is an ElevenLabs one)."""
    if is_vieneu(voice_id):
        return "vieneu"
    return "gemini" if is_gemini(voice_id) else "elevenlabs"


def service_name(voice_id: str | None) -> str:
    if is_vieneu(voice_id):
        return "VieNeu"
    return "Gemini" if is_gemini(voice_id) else "ElevenLabs"


def _model(voice: str) -> str:
    if is_vieneu(voice):
        return VIENEU_MODEL
    return GEMINI_MODEL if is_gemini(voice) else config.voice_model()


def voice_signature(voice_text: str, voice_id: str | None = None, speed: float = 1.0) -> str:
    """What one narration MP3 is made from. The speed joins only when it is not 1, so narration made before
    speeds existed stays valid; it joins as "tempo:<factor>", so narration made at an old preset ("tempo:fast")
    or while the speed was left to ElevenLabs (and ignored by eleven_v3) is made again."""
    voice = voice_id or config.voice_id()
    data = [voice, _model(voice), spoken_text(voice_text)]
    if speed != 1.0:
        data.append(f"tempo:{speed:g}")
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


NO_KEY = "Chưa có key ElevenLabs nên {}: nhập key ở Cài đặt › AI và nguồn tư liệu"
NO_VIENEU_KEY = "Chưa có key VieNeu nên {}: nhập key ở Cài đặt › AI và nguồn tư liệu"
NO_GEMINI_KEY = "Chưa có key Gemini nên {}: nhập key ở Cài đặt › AI và nguồn tư liệu (cùng key tạo ảnh AI)"


def synthesize(voice_text: str, key: str, voice_id: str | None = None, speed: float = 1.0) -> bytes:
    """The narration as MP3 bytes, in the given voice (the server's default when None) and speed (a tempo
    factor applied here with FFmpeg). `key` is the key of the voice's service (key_name) as source_keys gives it:
    pasted on the settings pages, else the .env one."""
    voice = voice_id or config.voice_id()
    if is_vieneu(voice):
        return change_speed(_vieneu_speech(voice_text, key, voice.removeprefix(VIENEU_PREFIX)), speed)
    if is_gemini(voice):
        return change_speed(_gemini_speech(voice_text, key, voice.removeprefix(GEMINI_PREFIX)), speed)
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
        return TtsError(
            "Key VieNeu không hợp lệ hoặc đã bị thu hồi: kiểm tra lại ở Cài đặt › AI và nguồn tư liệu", detail, True
        )
    if status == 429:
        if "trial" in lowered:
            return TtsError("Key VieNeu dùng thử đã hết lượt gọi trong ngày, thử lại sau 0 giờ", detail, True)
        return TtsError("VieNeu đang giới hạn lượt gọi, thử lại sau", detail)
    if status == 402 or "credit" in lowered or "quota" in lowered or "balance" in lowered:
        return TtsError("Tài khoản VieNeu đã hết lượt (credit), cần nạp thêm", detail, True)
    if status == 403:
        return TtsError("Tài khoản VieNeu chưa có gói API đang hoạt động", detail, True)
    if status == 400 and "voice" in lowered:
        return TtsError("VieNeu không có giọng đã chọn, hãy chọn giọng khác", detail)
    if status >= 500:
        return TtsError(f"VieNeu đang lỗi (HTTP {status}), thử lại sau", detail)
    return TtsError("VieNeu từ chối tạo lời đọc", detail)


def _gemini_speech(voice_text: str, key: str, voice: str) -> bytes:
    """Gemini TTS's MP3 for the text. Its answer is JSON holding a base64 WAV (24 kHz, mono), turned into MP3 here;
    the language is detected from the text, and the text is read verbatim (no style note is sent). A per-minute
    limit is waited out and the call made again; the daily one fails at once."""
    if not key:
        raise TtsError(NO_GEMINI_KEY.format("không tạo được lời đọc"))
    if voice not in GEMINI_VOICES:
        raise TtsError("Gemini không có giọng đã chọn, hãy chọn giọng khác", f"voice {voice!r}")
    payload = {
        "model": GEMINI_MODEL,
        "input": [{"type": "user_input", "content": [{"type": "text", "text": spoken_text(voice_text)}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    for attempt in range(GEMINI_RETRIES + 1):
        request = urllib.request.Request(
            f"{config.image_gen_api_url()}/v1beta/interactions",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            method="POST",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                answer = json.loads(response.read(MAX_AUDIO_BYTES * 2))
            break
        except urllib.error.HTTPError as err:
            body = err.read(4000).decode("utf-8", "replace")
            if err.code == 429 and not _gemini_daily_limit(body) and attempt < GEMINI_RETRIES:
                time.sleep(GEMINI_RETRY_SECONDS)
                continue
            raise _gemini_error(err.code, body) from None
        except OSError as err:
            raise TtsError("Không kết nối được Gemini, kiểm tra mạng rồi thử lại", str(err)) from None
        except ValueError as err:
            raise TtsError("Gemini trả file lời đọc không dùng được, thử lại sau", repr(err)) from None
    wav = _gemini_audio(answer)
    if not wav or len(wav) > MAX_AUDIO_BYTES:
        raise TtsError("Gemini trả file lời đọc không dùng được, thử lại sau", f"{len(wav)} bytes")
    return _wav_to_mp3(wav)


def _gemini_audio(answer: object) -> bytes:
    """The last audio block of the answer's steps, decoded; empty when there is none."""
    blocks = []
    steps = answer.get("steps") if isinstance(answer, dict) else None
    for step in steps if isinstance(steps, list) else []:
        content = step.get("content") if isinstance(step, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "audio" and isinstance(block.get("data"), str):
                blocks.append(block["data"])
    if not blocks:
        return b""
    try:
        return base64.b64decode(blocks[-1], validate=True)
    except (ValueError, binascii.Error):
        return b""


def _gemini_daily_limit(body: str) -> bool:
    """A 429 about the day's requests ("...RequestsPerDay...") rather than the minute's: waiting does not help."""
    lowered = body.lower()
    return "perday" in lowered or "per day" in lowered or "daily" in lowered


def _gemini_error(status: int, body: str) -> TtsError:
    detail = f"HTTP {status}: {body}"
    lowered = body.lower()
    if "api_key_invalid" in lowered or "api key not valid" in lowered or status == 401:
        return TtsError(
            "Key Gemini không hợp lệ hoặc đã bị thu hồi: kiểm tra lại ở Cài đặt › AI và nguồn tư liệu", detail, True
        )
    if status == 403:
        return TtsError(
            "Key Gemini không được phép đọc lời (chưa bật quyền hoặc bị giới hạn): kiểm tra ở AI Studio", detail, True
        )
    if status == 429:
        if _gemini_daily_limit(body):
            return TtsError(
                "Key Gemini đã hết lượt đọc lời trong ngày (làm mới khoảng 14–15 giờ Việt Nam): "
                "thử lại sau, hoặc chọn giọng ElevenLabs/VieNeu cho video này",
                detail,
                True,
            )
        return TtsError("Gemini đang giới hạn số lượt gọi mỗi phút, thử lại sau ít phút", detail)
    if status == 404:
        return TtsError("Gemini không có model đọc lời đã cấu hình", detail)
    if status == 400 and "voice" in lowered:
        return TtsError("Gemini không có giọng đã chọn, hãy chọn giọng khác", detail)
    if status >= 500:
        return TtsError(f"Gemini đang lỗi (HTTP {status}), thử lại sau", detail)
    return TtsError("Gemini từ chối tạo lời đọc", detail)


def _wav_to_mp3(data: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        source, output = Path(folder) / "voice.wav", Path(folder) / "voice.mp3"
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
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    str(output),
                ],
                "FFmpeg không đổi được lời đọc Gemini sang MP3",
            )
        except RenderError as err:
            raise TtsError("Gemini trả file lời đọc không dùng được, thử lại sau", str(err)) from None
        return output.read_bytes()


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
    lowered = body.lower()
    # A free plan cannot read library voices through the API: ElevenLabs answers HTTP 402 "paid_plan_required". It is
    # the key's plan, not its credit, so another key (a paid one, or the voice in its own account) may still read.
    if "paid_plan_required" in lowered or "library voice" in lowered:
        return TtsError(
            "Key ElevenLabs gói miễn phí không đọc được giọng thư viện qua API: dùng key gói trả phí hoặc chọn giọng "
            "có sẵn trong tài khoản của key này",
            detail,
            True,
        )
    # ElevenLabs says a spent plan with HTTP 401 and "quota_exceeded", so this comes before the 401 of a wrong key.
    if "quota" in lowered or status == 402:
        return TtsError("Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm", detail, True)
    if status == 401:
        return TtsError(
            "Key ElevenLabs không hợp lệ hoặc đã bị thu hồi: kiểm tra lại ở Cài đặt › AI và nguồn tư liệu", detail, True
        )
    if status == 404 and "voice_not_found" in lowered:
        # A voice lives in one account: a key of another account does not have it, but the next key may.
        return TtsError(
            "Tài khoản của key ElevenLabs này không có giọng đã chọn: thêm giọng đó vào tài khoản hoặc chọn giọng khác",
            detail,
            True,
        )
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


def list_gemini_voices(key: str) -> list[dict]:
    """Gemini TTS's prebuilt voices for the voice picker, each id prefixed with "gemini:". The list is fixed (Google
    publishes it, no call is made) and offered once the Gemini key is set, since reading them needs it."""
    if not key:
        raise TtsError(NO_GEMINI_KEY.format("chưa chọn được giọng Gemini"))
    return [
        {
            "id": GEMINI_PREFIX + name,
            "name": name,
            "description": description,
            "preview_url": None,
            "service": "gemini",
        }
        for name, description in sorted(GEMINI_VOICES.items())
    ]
