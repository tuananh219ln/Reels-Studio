"""The medical reminder of a health group's articles (decisions 2026-11-25, "medical disclaimer in the comment").

The caption carries no reminder: a group with `medical_disclaimer_enabled` and the position "last_comment" has its
fixed sentence added by the worker to the end of the last pinned comment when it is written (slot_comments.py). Never
stored in a comment's text, so editing a comment never drags it along and the sentence is changed in one place.

`strip` takes the sentence out of a caption (an old one, or one a member pasted) when the post text is built, and out
of an imported script's body; the caption stored in the database is never changed by it.
"""

import re

from .models import KnowledgeTopic

POSITIONS = ("last_comment", "caption")
DEFAULT_TEXT = (
    "(*) Thông tin chỉ mang tính tham khảo, không thay thế lời khuyên y khoa. "
    "Nếu có vấn đề về sức khỏe, bạn hãy hỏi ý kiến bác sĩ để được tư vấn phù hợp nhé."
)
MAX_TEXT = 1000
# Facebook's limit of one comment's text.
MAX_COMMENT = 8000
_PARAGRAPHS = re.compile(r"\n[ \t]*\n")
_MAX_PARAGRAPH = 300


def active(group: KnowledgeTopic | None) -> bool:
    """Whether the group's articles get the reminder in the last comment (and not in the caption)."""
    return bool(
        group
        and group.medical_disclaimer_enabled
        and group.medical_disclaimer_position == "last_comment"
        and text_of(group)
    )


def text_of(group: KnowledgeTopic | None) -> str:
    return ((group.medical_disclaimer_text or DEFAULT_TEXT) if group else "").strip()


def is_disclaimer(paragraph: str) -> bool:
    """A paragraph that reads as the reminder: it opens with "(*)", or it is short and says "tham khảo" together with
    "bác sĩ", "y khoa" or "chuyên gia" ("Bạn tham khảo cách làm dưới đây" is not one)."""
    text = paragraph.strip()
    if text.startswith("(*)"):
        return True
    lower = text.lower()
    return (
        len(text) < _MAX_PARAGRAPH
        and "tham khảo" in lower
        and any(word in lower for word in ("bác sĩ", "y khoa", "chuyên gia"))
    )


def has_disclaimer(text: str) -> bool:
    """Whether any paragraph of the text is the reminder (the first one, a caption's hook, only when it opens with
    "(*)")."""
    paragraphs = _PARAGRAPHS.split(text.strip())
    return any(
        paragraph.strip().startswith("(*)") if index == 0 else is_disclaimer(paragraph)
        for index, paragraph in enumerate(paragraphs)
    )


def strip(caption: str) -> str:
    """The caption without its reminder paragraphs, at most one blank line between the rest. The first paragraph is the
    hook (the text card's words) and only goes when it opens with "(*)"."""
    paragraphs = _PARAGRAPHS.split(caption.strip())
    kept = [
        paragraph.strip()
        for index, paragraph in enumerate(paragraphs)
        if paragraph.strip() and not (paragraph.strip().startswith("(*)") if index == 0 else is_disclaimer(paragraph))
    ]
    if len(kept) == len([p for p in paragraphs if p.strip()]):
        return caption.strip()
    return "\n\n".join(kept)


def clean_caption(group: KnowledgeTopic | None, caption: str) -> str:
    """The caption as posted and previewed: without the reminder when it goes to the last comment."""
    return strip(caption) if active(group) else caption.strip()


def attach(comment: str, group: KnowledgeTopic | None) -> tuple[str, bool]:
    """The text to write for the last comment, and whether the reminder needs a comment of its own: it is added after
    a blank line; left out when the comment already has one; a comment of its own when the two together would be
    over Facebook's limit."""
    if not active(group) or has_disclaimer(comment):
        return comment, False
    joined = f"{comment.rstrip()}\n\n{text_of(group)}"
    return (joined, False) if len(joined) <= MAX_COMMENT else (comment, True)
