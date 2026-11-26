"""A topic group's "Giọng đọc theo vai" (`knowledge_topics.voice_format`, migration 0127): which voice reads each role
of its videos, whether that voice comes from a TTS service or an uploaded file, and the group's narration rules.

It is stored and shown, not applied: scenes have no role, so whoever builds a video (a member or an assistant over
MCP) reads it and sets each scene's voice or uploads its file. `voice_id` stays the voice new videos start with and
`voice_backup_id` the voice read when a voice cannot be; this only adds roles, sources and rules.

    {"mode": "single" | "multi",
     "roles": [{"role": "all" | "op" | "comment" | "cta", "source": "provider" | "custom",
                "voice": "<voice id>", "voices": ["<voice id>", ...], "volume": 0-100, "note": "..."}],
     "rules": {"max_gemini_scenes": 0-50, "excited_tag": "..."}}

"single" has one role, "all"; "multi" names each role once and never "all". A "provider" role has a voice, and in
"multi" may rotate through `voices` instead (comments read in turn, an OP voice by vibe). A "custom" role's narration
is an uploaded file (POST /api/scenes/{id}/voice), so it names no voice.
"""

from .video_options import OptionError, clean_voice_id

MODES = ("single", "multi")
ROLES = ("all", "op", "comment", "cta")
SOURCES = ("provider", "custom")
MAX_VOICES = 10
MAX_NOTE_LENGTH = 300
MAX_GEMINI_SCENES = 50
ROLE_FIELDS = {"role", "source", "voice", "voices", "volume", "note"}
RULE_FIELDS = {"max_gemini_scenes", "excited_tag"}


def clean(value: object) -> dict:
    """The format as saved; {} for none. Unknown fields, roles and sources are refused with a message for members."""
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict) or set(value) - {"mode", "roles", "rules"}:
        raise OptionError("Giọng đọc theo vai không hợp lệ")
    mode = value.get("mode")
    if mode not in MODES:
        raise OptionError("Kiểu giọng phải là một giọng (single) hoặc nhiều giọng (multi)")
    roles = value.get("roles")
    if not isinstance(roles, list) or not roles:
        raise OptionError("Cần ít nhất một vai đọc")
    cleaned = [_role(role, mode) for role in roles]
    names = [role["role"] for role in cleaned]
    if len(set(names)) != len(names):
        raise OptionError("Mỗi vai chỉ khai một lần")
    if mode == "single" and names != ["all"]:
        raise OptionError("Kiểu một giọng chỉ có một vai “all” (cả video)")
    if mode == "multi" and "all" in names:
        raise OptionError("Kiểu nhiều giọng khai từng vai (op, comment, cta), không dùng vai “all”")
    result = {"mode": mode, "roles": cleaned}
    if rules := _rules(value.get("rules")):
        result["rules"] = rules
    return result


def _role(value: object, mode: str) -> dict:
    if not isinstance(value, dict) or set(value) - ROLE_FIELDS:
        raise OptionError("Vai đọc không hợp lệ")
    name = value.get("role")
    if name not in ROLES:
        raise OptionError(f"Vai “{name}” không có: chỉ nhận {', '.join(ROLES)}")
    source = value.get("source", "provider")
    if source not in SOURCES:
        raise OptionError(
            f"Nguồn giọng “{source}” không có: chỉ nhận provider (dịch vụ đọc) hoặc custom (file tải lên)"
        )
    role: dict = {"role": name, "source": source}
    voice = _voice(value.get("voice", ""))
    voices = value.get("voices") or []
    if not isinstance(voices, list) or len(voices) > MAX_VOICES:
        raise OptionError(f"Danh sách giọng xoay vòng tối đa {MAX_VOICES} giọng")
    voices = list(dict.fromkeys(_voice(item) for item in voices if item != ""))
    if source == "custom":
        if voice or voices:
            raise OptionError(f"Vai “{name}” dùng file tải lên nên không chọn giọng")
    elif voices:
        if mode == "single":
            raise OptionError("Kiểu một giọng không xoay vòng giọng")
        role["voices"] = voices
        if voice:
            role["voice"] = voice
    elif voice:
        role["voice"] = voice
    else:
        raise OptionError(f"Vai “{name}” chưa có giọng")
    if "volume" in value:
        volume = value["volume"]
        if isinstance(volume, bool) or not isinstance(volume, int) or not 0 <= volume <= 100:
            raise OptionError("Âm lượng giọng là số nguyên từ 0 đến 100")
        role["volume"] = volume
    if note := _text(value.get("note", ""), "Ghi chú của vai"):
        role["note"] = note
    return role


def _rules(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - RULE_FIELDS:
        raise OptionError("Luật giọng đọc không hợp lệ")
    rules: dict = {}
    if value.get("max_gemini_scenes") is not None:
        limit = value["max_gemini_scenes"]
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= MAX_GEMINI_SCENES:
            raise OptionError(f"Số cảnh Gemini tối đa là số nguyên từ 0 đến {MAX_GEMINI_SCENES}")
        rules["max_gemini_scenes"] = limit
    if tag := _text(value.get("excited_tag", ""), "Luật thẻ [excited]"):
        rules["excited_tag"] = tag
    return rules


def _voice(value: object) -> str:
    try:
        return clean_voice_id(value)
    except OptionError:
        raise OptionError(f"Mã giọng “{value}” không hợp lệ") from None


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise OptionError(f"{label} phải là chữ")
    value = " ".join(value.split())
    if len(value) > MAX_NOTE_LENGTH:
        raise OptionError(f"{label} dài quá {MAX_NOTE_LENGTH} ký tự")
    return value
