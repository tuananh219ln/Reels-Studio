"""The spoken words of a sample video ("Từ video mẫu", reference.py), through ElevenLabs Speech-to-Text (Scribe).

The same ElevenLabs key as narration (Cài đặt › Nguồn tư liệu, else ELEVENLABS_API_KEY). The language is left to
ElevenLabs to detect, since a sample may be in any language. The words come back with their seconds, grouped here
into lines that start with the second they are said at, so the AI can tie them to the stills.
"""

from pathlib import Path

import httpx

from . import config
from .tts import TtsError

MODEL = "scribe_v2"
REQUEST_TIMEOUT = 180
# A new line starts after a sentence ends or after this many seconds of words.
LINE_SECONDS = 6.0
SENTENCE_ENDS = (".", "!", "?", "…")


def transcribe(audio: Path, key: str) -> str:
    """The words as lines "[m:ss] ...", or "" when nothing is said. Failures raise TtsError with a member message."""
    url = f"{config.elevenlabs_api_url()}/v1/speech-to-text"
    try:
        with open(audio, "rb") as file:
            response = httpx.post(
                url,
                headers={"xi-api-key": key},
                data={"model_id": MODEL, "timestamps_granularity": "word"},
                files={"file": (audio.name, file, "audio/mpeg")},
                timeout=REQUEST_TIMEOUT,
            )
    except httpx.TimeoutException:
        raise TtsError("ElevenLabs không chuyển lời thoại kịp, thử lại sau") from None
    except httpx.HTTPError as err:
        raise TtsError("Không kết nối được ElevenLabs, kiểm tra mạng rồi thử lại", str(err)) from None
    if response.status_code != 200:
        raise _error(response.status_code, response.text[:4000])
    try:
        words = response.json().get("words") or []
    except ValueError:
        raise TtsError("ElevenLabs trả lời thoại không đúng dạng", response.text[:4000]) from None
    return lines(words)


def lines(words: list) -> str:
    """ElevenLabs' words ({"text", "start", "type"}) as timed lines; spacing and audio events are dropped."""
    out: list[str] = []
    current: list[str] = []
    start: float | None = None
    for word in words:
        if not isinstance(word, dict) or word.get("type") not in (None, "word"):
            continue
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        second = word.get("start")
        second = float(second) if isinstance(second, (int, float)) else (start or 0.0)
        if start is None:
            start = second
        current.append(text)
        if text.endswith(SENTENCE_ENDS) or second - start >= LINE_SECONDS:
            out.append(_line(start, current))
            current, start = [], None
    if current:
        out.append(_line(start or 0.0, current))
    return "\n".join(out)


def _line(second: float, words: list[str]) -> str:
    whole = int(second)
    return f"[{whole // 60}:{whole % 60:02d}] {' '.join(words)}"


def _error(status: int, body: str) -> TtsError:
    detail = f"HTTP {status}: {body}"
    if "quota" in body.lower() or status == 402:
        return TtsError("Tài khoản ElevenLabs đã hết hạn mức, cần nạp thêm để tách lời thoại", detail)
    if status == 401 and ("missing_permissions" in body or "speech_to_text" in body):
        return TtsError(
            "Key ElevenLabs chưa bật quyền Speech to Text: bật quyền này cho key ở trang ElevenLabs", detail
        )
    if status == 401:
        return TtsError("Key ElevenLabs không hợp lệ: kiểm tra lại ở Cài đặt › Nguồn tư liệu", detail)
    if status == 429:
        return TtsError("ElevenLabs đang giới hạn lượt gọi, thử lại sau", detail)
    if status >= 500:
        return TtsError(f"ElevenLabs đang lỗi (HTTP {status}), thử lại sau", detail)
    return TtsError("ElevenLabs từ chối tách lời thoại", detail)
