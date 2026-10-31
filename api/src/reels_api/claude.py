"""Script writing: the prompt and turning the LLM's answer into a checked script (the call is in llm.py).

Members edit only the prompt's content on /knowledge. The output format below is fixed in code, so
an edited prompt can never break the JSON every job depends on.
"""

import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

TOPIC_PLACEHOLDER = "[Chủ đề]"
MAX_KEYWORD_LENGTH = 100
FALLBACK_SECONDS = 4

OUTPUT_FORMAT = """\
ĐỊNH DẠNG ĐẦU RA (bắt buộc): chỉ trả về đúng một object JSON, không kèm chữ nào khác, không bọc trong ```.
Các trường:
- "titles": 5 tiêu đề viết hoa, mỗi tiêu đề tối đa 12 từ.
- "title_voice": lời đọc cho cảnh tiêu đề: một câu mở đầu gây tò mò về chủ đề chung, hợp với cả 5 tiêu đề (không đọc lại
  nguyên văn tiêu đề nào), 8–12 từ.
  Khi đọc, mỗi cảnh được đọc chữ trên màn hình trước rồi mới đến lời đọc của cảnh đó, nên lời đọc nói tiếp ý, không lặp
  lại chữ trên màn hình. Tổng số từ của tiêu đề dài nhất, "title_voice", mọi "text" và mọi "voice" không quá 120 từ:
  nhiều cảnh thì viết mỗi lời gần 6 từ, ít cảnh mới viết gần 12 từ.
- "title_keywords": 2–4 từ khóa tiếng Việt để tìm ảnh chụp cho cảnh tiêu đề, xếp từ cụ thể đến chung
  (món tiêu biểu nhất của chủ đề trước, nhóm món sau).
- "title_keywords_en": 2–4 từ khóa tiếng Anh tương ứng để tìm ở các kho ảnh phương Tây (Pixabay, Pexels —
  hai kho này đánh chỉ mục bằng tiếng Anh): dịch tên món/nguyên liệu sang tiếng Anh phổ thông, xếp từ cụ thể
  đến chung, không để tên riêng tiếng Việt.
- "scenes": 5–7 cảnh nội dung theo thứ tự. Mỗi cảnh có:
  - "text": chữ trên màn hình, tối đa 10 từ; bọc từ khóa cần tô đỏ trong *dấu sao*; xuống dòng bằng \\n
    (không để dòng trống, không kết thúc bằng \\n);
  - "seconds": số giây của cảnh (3–5);
  - "voice": lời đọc của cảnh, câu nói tự nhiên nối tiếp chữ trên màn hình của cảnh đó và chi tiết hơn một chút (thêm
    lý do, cách ăn hoặc mẹo nhỏ), 6–12 từ; không dùng *dấu sao*, viết số và đơn vị thành chữ khi cần đọc rõ;
  - "image_prompt": prompt tạo ảnh 9:16 (ảnh thực, ánh sáng tự nhiên, bàn gỗ);
  - "keywords": 2–4 từ khóa tiếng Việt để tìm ảnh chụp cho cảnh, xếp từ cụ thể đến chung
    (tên món/nguyên liệu cụ thể của cảnh trước, nhóm chung sau).
  - "keywords_en": 2–4 từ khóa tiếng Anh tương ứng cho các kho ảnh phương Tây: dịch tên món/nguyên liệu
    sang tiếng Anh phổ thông, xếp từ cụ thể đến chung, không để tên riêng tiếng Việt.
- "caption": caption theo yêu cầu trong prompt; không có yêu cầu thì viết ngắn gọn.
- "hashtags": đúng 5 hashtag, mỗi hashtag bắt đầu bằng #.
- "affiliates": 2 sản phẩm affiliate phù hợp, mỗi sản phẩm một chuỗi.
- "pinned_comment": câu bình luận ghim.
- "self_review": danh sách các câu đã sửa khi tự rà soát an toàn (mỗi mục ghi câu cũ → câu mới); để [] nếu không sửa gì.
- "music_suggestions": 2–3 tên bản nhạc không lời hợp chủ đề, có thể tìm trong thư viện nhạc TikTok/Facebook.

Ví dụ đầy đủ:
{
  "titles": [
    "5 MÓN GIÚP XƯƠNG CHẮC KHỎE SAU TUỔI 50",
    "SAU 50 TUỔI ĐỪNG ĐỂ BỮA CƠM THIẾU 5 MÓN NÀY",
    "5 MÓN QUEN THUỘC TỐT CHO XƯƠNG KHỚP NGƯỜI LỚN TUỔI",
    "ĂN GÌ ĐỂ XƯƠNG CHẮC KHỎE SAU TUỔI 50?",
    "5 THỰC PHẨM GIÀU CANXI DỄ TÌM CHO NGƯỜI 50+"
  ],
  "title_voice": "Xương yếu dần theo năm tháng, bữa cơm đã đủ chưa?",
  "title_keywords": ["cá cơm chiên giòn", "món ăn giàu canxi"],
  "title_keywords_en": ["fried whitebait", "calcium rich food"],
  "scenes": [
    {"text": "Cá nhỏ ăn cả xương\\nGiàu *canxi*, rẻ, dễ tìm", "seconds": 4,
     "voice": "Chiên giòn hay kho nhạt đều rất hợp bữa cơm.",
     "image_prompt": "Đĩa cá cơm chiên giòn trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16",
     "keywords": ["cá cơm chiên giòn", "cá nhỏ", "món cá"],
     "keywords_en": ["fried whitebait", "small fish", "fish dish"]},
    {"text": "Sữa chua\\nBổ sung *canxi* và đạm", "seconds": 4,
     "voice": "Mỗi ngày một hũ, lại dễ ăn cho người lớn tuổi.",
     "image_prompt": "Hũ sữa chua trắng trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16",
     "keywords": ["hũ sữa chua", "sữa chua"],
     "keywords_en": ["yogurt cup", "yogurt"]},
    {"text": "Đậu phụ\\nCanxi và *đạm thực vật*", "seconds": 4,
     "voice": "Món quen thuộc, rán hay nấu canh đều ngon.",
     "image_prompt": "Đĩa đậu phụ rán vàng trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16",
     "keywords": ["đậu phụ rán", "đậu phụ", "món đậu"],
     "keywords_en": ["fried tofu", "tofu", "tofu dish"]},
    {"text": "Rau cải xanh\\nCó canxi và *vitamin K*", "seconds": 4,
     "voice": "Nên có mặt trong bữa cơm để xương chắc khỏe hơn.",
     "image_prompt": "Bó rau cải xanh tươi trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16",
     "keywords": ["rau cải xanh", "rau xanh"],
     "keywords_en": ["green vegetables", "leafy greens"]},
    {"text": "Vừng đen\\nRắc vào cháo, *sữa hạt* mỗi sáng", "seconds": 4,
     "voice": "Chỉ một chút thôi, vừa thơm vừa bổ sung canxi.",
     "image_prompt": "Bát vừng đen rang trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16",
     "keywords": ["vừng đen rang", "vừng đen"],
     "keywords_en": ["black sesame seeds", "black sesame"]}
  ],
  "caption": "5 món giúp xương chắc khỏe sau tuổi 50! Nhà bạn hay ăn món nào nhất?",
  "hashtags": ["#xuongkhop", "#duongsinh", "#dinhduong", "#nguoicaotuoi", "#canxi"],
  "affiliates": ["Sữa hạt bổ sung canxi cho người lớn tuổi", "Vừng đen rang sẵn đóng hũ"],
  "pinned_comment": "Món nào nhà bạn hay ăn nhất? Link sản phẩm trong bình luận ghim nhé!",
  "self_review": ["\\"chữa khỏi loãng xương\\" → \\"tốt cho xương chắc khỏe\\""],
  "music_suggestions": ["Windy Hill", "Morning Coffee (piano)", "Nhạc không lời thư giãn"]
}"""


class ClaudeError(Exception):
    """The LLM call failed or its answer was unusable; `message` is shown to members, `detail` is diagnostic.

    Named for Claude, the first provider; every provider in llm.py raises it."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ScriptOutputError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedScene:
    text: str
    seconds: float
    keywords: list[str]
    image_prompt: str
    voice: str = ""
    keywords_en: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GeneratedScript:
    titles: list[str]
    title_keywords: list[str]
    scenes: list[GeneratedScene]
    title_voice: str = ""
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    affiliates: list[str] = field(default_factory=list)
    pinned_comment: str = ""
    self_review: list[str] = field(default_factory=list)
    music_suggestions: list[str] = field(default_factory=list)
    title_keywords_en: list[str] = field(default_factory=list)


def build_script_prompt(template: str, topic: str, banned_words: list[str]) -> str:
    return _assemble(_fill(template, [(TOPIC_PLACEHOLDER, "Chủ đề", topic)]), banned_words)


def build_clone_prompt(template: str, source: dict, banned_words: list[str]) -> str:
    """`source` is the snapshot taken when "Nhân bản" was pressed (see routes_videos.clone_snapshot)."""
    return _assemble(
        _fill(
            template,
            [
                ("[tiêu đề]", "Tiêu đề video gốc", source["title"]),
                ("[chủ đề]", "Chủ đề video gốc", source["topic"]),
                ("[kịch bản đã sửa của video gốc]", "Kịch bản đã sửa của video gốc", source["script"]),
                ("[yêu cầu đổi]", "Yêu cầu đổi", source["request"]),
            ],
        ),
        banned_words,
    )


def _fill(template: str, placeholders: list[tuple[str, str, str]]) -> str:
    """Replace each placeholder; one a member deleted from the prompt is appended at the end instead."""
    body, missing = template, []
    for placeholder, label, value in placeholders:
        if placeholder in body:
            body = body.replace(placeholder, value)
        else:
            missing.append(f"{label}: {value}")
    return "\n\n".join([body.rstrip(), *missing]) if missing else body


def _assemble(body: str, banned_words: list[str]) -> str:
    parts = [body]
    if banned_words:
        quoted = ", ".join(f'"{word}"' for word in banned_words)
        parts.append(
            f"Từ cấm, không được dùng trong tiêu đề, chữ trên màn hình, lời đọc, caption và bình luận ghim: {quoted}."
        )
    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)


def parse_output(raw: str) -> GeneratedScript:
    """Claude's JSON as a script. Broken JSON, no title or no scene raise; small slips are repaired."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ScriptOutputError("câu trả lời không có object JSON")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as err:
        raise ScriptOutputError(f"JSON lỗi cú pháp: {err.msg} (dòng {err.lineno}, cột {err.colno})") from None
    if not isinstance(data, dict):
        raise ScriptOutputError("JSON không phải object")
    titles = _strings(data.get("titles"))[:5]
    if not titles:
        raise ScriptOutputError("thiếu tiêu đề")
    scenes = (
        [_scene(item) for item in data.get("scenes") or [] if isinstance(item, dict)]
        if isinstance(data.get("scenes"), list)
        else []
    )
    if not scenes:
        raise ScriptOutputError("không có cảnh nội dung nào")
    return GeneratedScript(
        titles=titles,
        title_keywords=_keywords(data.get("title_keywords")),
        scenes=scenes,
        title_voice=_voice(data.get("title_voice")),
        caption=_text(data.get("caption")),
        hashtags=_strings(data.get("hashtags")),
        affiliates=_strings(data.get("affiliates")),
        pinned_comment=_text(data.get("pinned_comment")),
        self_review=_strings(data.get("self_review")),
        music_suggestions=_strings(data.get("music_suggestions")),
        title_keywords_en=_keywords(data.get("title_keywords_en")),
    )


def _scene(item: dict) -> GeneratedScene:
    seconds = item.get("seconds")
    valid = isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds)
    return GeneratedScene(
        text=_text(item.get("text")),
        seconds=float(seconds) if valid and seconds >= 1 else FALLBACK_SECONDS,
        keywords=_keywords(item.get("keywords")),
        image_prompt=_text(item.get("image_prompt")),
        voice=_voice(item.get("voice")),
        keywords_en=_keywords(item.get("keywords_en")),
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _voice(value: object) -> str:
    # A stray *markup* star would be read aloud or skipped unpredictably.
    return " ".join(_text(value).replace("*", "").split())


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, dict):
            item = " — ".join(str(part) for part in item.values() if isinstance(part, (str, int, float)))
        if isinstance(item, (str, int, float)) and not isinstance(item, bool) and str(item).strip():
            items.append(str(item).strip())
    return items


def _keywords(value: object) -> list[str]:
    return [keyword[:MAX_KEYWORD_LENGTH].strip() for keyword in _strings(value)]


def generate_script(
    prompt: str, label: str, on_call: Callable[[], None], call: Callable[[str, str], str]
) -> GeneratedScript:
    """Ask once more when the answer is unusable, then give up with the raw answer as the detail."""
    for attempt in (1, 2):
        raw = call(prompt, label)
        on_call()
        try:
            return parse_output(raw)
        except ScriptOutputError as err:
            log.warning("LLM answer unusable for %s (attempt %d): %s\n%s", label, attempt, err, raw[:4000])
            problem = err
    raise ClaudeError(
        f"AI trả kịch bản không đúng định dạng ({problem}), đã thử lại 1 lần",
        f"Câu trả lời thô:\n{raw[:8000]}",
    )
