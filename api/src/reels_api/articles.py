"""Articles ("Bài viết"): photo or text posts for a Page, a cheap test of a topic before a reel is made.

The caption is typed by a member or written by the AI in an `article_caption` job, assembled by the same
`claude._assemble` as a video script, with this module's fixed output format. Its checks follow the video's: a banned
word only warns (decisions 2026-10-31); a link in the caption or pinned comment blocks, because the app adds the
affiliate links itself, in the comment only. The AI writes its own reminder to ask a doctor, in the post's voice; no
fixed sentence is added (decisions 2026-11-07). A picture is optional: a "Thẻ chữ" (text card drawn here), a pasted photo's link, or none.
"""

import io
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from reels_render.textbox import FONT_PATH

from . import hashtags as hashtag_rules
from . import knowledge
from .claude import ClaudeError, ScriptOutputError, _assemble, _strings, fill_placeholders, json_object
from .models import ACTIVE_JOB_STATUSES, Article, Job, KnowledgeTopic, PageComment
from .script_rules import banned_hits

KIND_LABELS = {
    "kien_thuc": "Kiến thức ngắn",
    "meo": "Mẹo vặt",
    "cau_hoi": "Câu hỏi / thăm dò",
    "canh_bao": "Cảnh báo / nhắc nhở",
    "tra_loi_binh_luan": "Trả lời bình luận",
    "checklist": "Tổng hợp / danh sách",
}
IMAGE_KIND_LABELS = {"ai": "Ảnh AI", "link": "Ảnh từ link", "text_card": "Thẻ chữ"}
MAX_HASHTAGS = 5
MAX_IDEAS = 3
MAX_PINNED_LENGTH = 2000
MAX_TOPIC_LENGTH = 300
MAX_CAPTION_LENGTH = 5000
# A link in the caption: a scheme, "www." or a bare domain such as shope.ee/abc or example.com.
LINK = re.compile(
    r"(https?://|www\.)\S+|\b[a-z0-9-]+\.(?:com|vn|net|org|me|ly|ee|co|io|link|shop)\b(?:/\S*)?", re.IGNORECASE
)

PLACEHOLDERS = (
    ("[Nhóm chủ đề]", "Nhóm chủ đề"),
    ("[Dạng bài]", "Dạng bài"),
    ("[Chủ đề]", "Chủ đề"),
    ("[Bình luận gốc]", "Bình luận của người xem cần trả lời"),
)
ARTICLE_TEXTS = "dòng mở đầu, nội dung, câu nhắc, câu hỏi, hashtag và bình luận ghim của bài viết"

_FORMAT = """\
Chỉ trả về đúng một object JSON, không có chữ nào khác ngoài JSON:
{{
  "hook": "1 dòng mở đầu",
  "body": "{body}",
  "note": "1 câu nhắc nhẹ, hoặc chuỗi rỗng",
  "question": "1 câu hỏi kết bài cho người xem trả lời trong bình luận",
  "hashtags": ["#tối_đa_5_hashtag"],
  "pinned_comment": "bình luận ghim của Page dưới bài",
  "affiliates": ["tối đa {max_ideas} sản phẩm để tìm trên Shopee"]
}}
Quy tắc định dạng:
- {hook_rule}
- {body_rule}
- "note": khi bài nói về sức khỏe, ăn uống hay thói quen cơ thể, viết 1 câu nhắc ngắn bằng giọng của bài, như người quen dặn nhau (ví dụ ý: ai có bệnh nền, đang mang thai hay đang dùng thuốc thì hỏi bác sĩ trước). Không dùng câu khuôn mẫu kiểu "tham khảo, không thay thế tư vấn bác sĩ". Bài không cần nhắc thì để chuỗi rỗng.
- "pinned_comment": 1–2 câu Page tự bình luận dưới bài để ghim: gợi chuyện tiếp, mời người xem kể trải nghiệm hoặc hỏi thêm; nếu có sản phẩm hợp với bài thì nói nhẹ là link ở ngay bên dưới. Không link, không số điện thoại.
- "affiliates": 0–{max_ideas} sản phẩm thật sự hợp với nội dung bài, mỗi cái là vài chữ để gõ vào ô tìm kiếm Shopee (ví dụ "bình giữ nhiệt", "gối cao su non"); không hợp thì để mảng rỗng.
- Không viết link, tên miền hay số điện thoại trong bài; link sản phẩm (nếu có) nằm ở bình luận ghim.
- Tối đa {max_tags} hashtag, mỗi hashtag bắt đầu bằng #, không dấu cách bên trong; không chèn hashtag vào câu."""


def output_format(kind: str) -> str:
    """The fixed shape of the AI's answer for this kind of article (code, not prompt: "Prompt text is app data")."""
    if kind == "cau_hoi":
        body = "để trống"
        body_rule = 'Dạng câu hỏi: "body" để chuỗi rỗng, chỉ có dòng mở đầu và câu hỏi.'
    elif kind == "checklist":
        body = "3–5 dòng, mỗi dòng một ý"
        body_rule = '"body" là 3–5 dòng, mỗi dòng một ý ngắn, bắt đầu bằng "- ".'
    else:
        body = "3–5 dòng nội dung"
        body_rule = '"body" là 3–5 dòng ngắn, xuống dòng giữa các ý.'
    hook_rule = (
        "Dòng mở đầu nhắc lại ngắn gọn câu hỏi hoặc bình luận của người xem, rồi mới trả lời."
        if kind == "tra_loi_binh_luan"
        else "Dòng mở đầu là 1 câu, dưới 15 từ."
    )
    return _FORMAT.format(
        body=body, body_rule=body_rule, hook_rule=hook_rule, max_tags=MAX_HASHTAGS, max_ideas=MAX_IDEAS
    )


def default_prompt() -> str:
    return knowledge.default_article_prompt()


def build_prompt(group: KnowledgeTopic | None, article: Article, comment: str = "") -> str:
    template = (group.article_prompt if group else "") or default_prompt()
    values = [group.name if group else "", KIND_LABELS[article.kind], article.topic, comment]
    placeholders = [
        (placeholder, label, value) for (placeholder, label), value in zip(PLACEHOLDERS, values, strict=True) if value
    ]
    return _assemble(
        fill_placeholders(template, placeholders),
        group.banned_words if group else [],
        output_format=output_format(article.kind),
        texts=ARTICLE_TEXTS,
    )


@dataclass(frozen=True)
class GeneratedCaption:
    caption: str
    hashtags: list[str]
    pinned_comment: str = ""
    affiliates: list[str] = field(default_factory=list)


def _line(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _lines(value: object) -> str:
    if isinstance(value, list):
        value = "\n".join(str(item) for item in value if isinstance(item, (str, int, float)))
    if not isinstance(value, str):
        return ""
    return "\n".join(line.strip() for line in value.strip().splitlines() if line.strip())


def compose_caption(hook: str, body: str, question: str, note: str = "") -> str:
    """Hook, body (closed by the AI's own reminder, when it wrote one) and question, each a paragraph of its own."""
    middle = "\n".join(part for part in (body, note) if part)
    return "\n\n".join(part for part in (hook, middle, question) if part)


def parse_output(raw: str, kind: str) -> GeneratedCaption:
    data = json_object(raw)
    hook, question = _line(data.get("hook")), _line(data.get("question"))
    body = "" if kind == "cau_hoi" else _lines(data.get("body"))
    if not hook:
        raise ScriptOutputError("thiếu dòng mở đầu")
    if not question:
        raise ScriptOutputError("thiếu câu hỏi kết bài")
    if kind != "cau_hoi" and not body:
        raise ScriptOutputError("thiếu nội dung")
    tags = data.get("hashtags")
    tags = [tags] if isinstance(tags, str) else tags if isinstance(tags, list) else []
    ideas = [_line(idea)[:100] for idea in _strings(data.get("affiliates"))]
    return GeneratedCaption(
        compose_caption(hook, body, question, _line(data.get("note"))),
        clean_hashtags([str(tag) for tag in tags]),
        _lines(data.get("pinned_comment"))[:MAX_PINNED_LENGTH],
        [idea for idea in ideas if idea][:MAX_IDEAS],
    )


def generate(prompt: str, kind: str, label: str, on_call: Callable[[], None], call) -> GeneratedCaption:
    """Asked once more when the answer is unusable, then given up with the raw answer as the detail."""
    for _attempt in (1, 2):
        raw = call(prompt, label)
        on_call()
        try:
            return parse_output(raw, kind)
        except ScriptOutputError as err:
            problem = err
    raise ClaudeError(
        f"AI trả bài viết không đúng định dạng ({problem}), đã thử lại 1 lần", f"Câu trả lời thô:\n{raw[:8000]}"
    )


def clean_hashtags(tags: list[str]) -> list[str]:
    """`#` in front, no spaces, no repeats (case ignored), at most MAX_HASHTAGS; words that are not hashtags go."""
    cleaned: list[str] = []
    for tag in tags:
        word = "".join(tag.split())
        if word and not word.startswith("#"):
            word = f"#{word}"
        if hashtag_rules.TAG.fullmatch(word):
            cleaned = hashtag_rules.merge(cleaned, [word])
    return cleaned[:MAX_HASHTAGS]


def hook_of(caption: str) -> str:
    """The caption's first line: what a text card shows."""
    return next((line.strip() for line in caption.splitlines() if line.strip()), "")


# --- Checks ---


@dataclass
class Issue:
    message: str
    field: str = "caption"


def checks(article: Article, banned_words: list[str]) -> dict:
    """`blocking` will stop "Đăng" (a link in the caption, no caption); `warnings` never do (decisions 2026-10-31)."""
    blocking: list[Issue] = []
    warnings: list[Issue] = []
    text = "\n".join([article.caption, " ".join(article.hashtags)])
    comment_hits = banned_hits(article.pinned_comment, banned_words)
    if not article.caption.strip():
        blocking.append(Issue("Chưa có caption"))
    if LINK.search(text):
        blocking.append(Issue("Caption có link: link sản phẩm chỉ để ở bình luận ghim"))
    for word in banned_hits(text, banned_words):
        warnings.append(Issue(f"Có từ cấm: “{word}”"))
    for word in comment_hits:
        warnings.append(Issue(f"Bình luận ghim có từ cấm: “{word}”", "pinned_comment"))
    if LINK.search(article.pinned_comment):
        blocking.append(Issue("Bình luận ghim có link: link sản phẩm do app tự thêm sau bình luận", "pinned_comment"))
    if article.kind == "tra_loi_binh_luan" and article.source_comment_id is None:
        warnings.append(Issue("Chưa chọn bình luận được trả lời", "source_comment_id"))
    return {
        "blocking": [issue.__dict__ for issue in blocking],
        "warnings": [issue.__dict__ for issue in warnings],
    }


# --- Text card ("Thẻ chữ") ---

CARD_SIZE = (1080, 1350)  # 4:5, the tallest a photo shows in Facebook's feed without being cropped
CARD_PRESETS = {
    "cam": ("Cam", "#f26b1d", "#ffffff"),
    "xanh_la": ("Xanh lá", "#2f7d4f", "#ffffff"),
    "kem": ("Kem", "#f7efe1", "#3a2a1a"),
    "dem": ("Đêm", "#1f2a37", "#fff4d6"),
}
DEFAULT_CARD_PRESET = "cam"
CARD_MARGIN = 100
MAX_CARD_CHARS = 200


class CardError(ValueError):
    pass


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        words, line = paragraph.split(), ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if font.getlength(candidate) <= width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines


def text_card(text: str, preset: str) -> bytes:
    """A JPEG of `text` centred on the preset's colour, in the app's font (Be Vietnam Pro, which has every
    Vietnamese letter), as large as fits."""
    text = " ".join(text.split())
    if not text:
        raise CardError("Chưa có chữ cho thẻ: viết caption trước (dòng đầu là chữ trên thẻ)")
    if len(text) > MAX_CARD_CHARS:
        raise CardError(f"Chữ trên thẻ dài quá {MAX_CARD_CHARS} ký tự, hãy rút ngắn dòng đầu của caption")
    if preset not in CARD_PRESETS:
        raise CardError("Màu thẻ không hợp lệ")
    _, background, colour = CARD_PRESETS[preset]
    width, height = CARD_SIZE
    room_w, room_h = width - 2 * CARD_MARGIN, height - 2 * CARD_MARGIN
    for size in range(110, 39, -6):
        font = ImageFont.truetype(str(FONT_PATH), size)
        lines = _wrap(text, font, room_w)
        spacing = round(size * 0.35)
        block = len(lines) * size + (len(lines) - 1) * spacing
        if block <= room_h and all(font.getlength(line) <= room_w for line in lines):
            break  # the smallest size is used when none fits; MAX_CARD_CHARS keeps it on the card
    image = Image.new("RGB", CARD_SIZE, background)
    draw = ImageDraw.Draw(image)
    y = (height - block) / 2
    for line in lines:
        draw.text(((width - font.getlength(line)) / 2, y), line, font=font, fill=colour)
        y += size + spacing
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def new_key(article_id: int, name: str, extension: str) -> str:
    return f"articles/{article_id}/{name}-{secrets.token_hex(6)}.{extension}"


# --- Jobs and payload ---


def active_job(db: DbSession, article_id: int) -> Job | None:
    return db.scalar(select(Job).where(Job.article_id == article_id, Job.status.in_(ACTIVE_JOB_STATUSES)))


def last_job(db: DbSession, article_id: int) -> Job | None:
    return db.scalar(
        select(Job).where(Job.article_id == article_id, Job.kind == "article_caption").order_by(Job.id.desc()).limit(1)
    )


def enqueue_caption(db: DbSession, article: Article, user_id: int, retry_of_id: int | None = None) -> bool:
    """False when the article already has a job queued or running (the partial unique index is the guard), after
    rolling the transaction back."""
    db.add(
        Job(
            article_id=article.id,
            kind="article_caption",
            status="queued",
            created_by_id=user_id,
            retry_of_id=retry_of_id,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def group_of(db: DbSession, article: Article) -> KnowledgeTopic | None:
    return db.get(KnowledgeTopic, article.knowledge_topic_id) if article.knowledge_topic_id else None


def comment_text(comment: PageComment | None) -> str:
    return f"{comment.author_name}: {comment.message}" if comment else ""


def payload(db: DbSession, article: Article) -> dict:
    group = group_of(db, article)
    job = last_job(db, article.id)
    comment = article.source_comment
    return {
        "id": article.id,
        "knowledge_topic_id": article.knowledge_topic_id,
        "group_name": group.name if group else None,
        "kind": article.kind,
        "kind_label": KIND_LABELS[article.kind],
        "topic": article.topic,
        "caption": article.caption,
        "hashtags": article.hashtags,
        "pinned_comment": article.pinned_comment,
        "affiliates": article.affiliates,
        # The Shopee search of its product ideas, as a video's `suggest`.
        "suggest": {
            "state": "pending" if article.suggest_requested_at else ("failed" if article.suggest_error else "idle"),
        },
        "hook": hook_of(article.caption),
        "has_image": bool(article.image_key),
        "image_kind": article.image_kind,
        "image_kind_label": IMAGE_KIND_LABELS.get(article.image_kind or ""),
        "image_source": article.image_source,
        "image_version": article.image_key.rsplit("-", 1)[-1] if article.image_key else None,
        "source_comment": {"id": comment.id, "author": comment.author_name, "message": comment.message}
        if comment
        else None,
        "status": "draft",
        "status_label": "Nháp",
        "job": {
            "id": job.id,
            "status": job.status,
            "error": job.error,
        }
        if job
        else None,
        "busy": job is not None and job.status in ACTIVE_JOB_STATUSES,
        "checks": checks(article, group.banned_words if group else []),
        "created_by": article.created_by.name,
        "created_at": article.created_at.isoformat(),
        "updated_at": article.updated_at.isoformat(),
    }
