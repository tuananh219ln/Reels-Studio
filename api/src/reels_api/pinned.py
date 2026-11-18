"""The pinned comment, always the same three parts (docs/decisions/2026-11-19-pinned-comment-fixed-shape.md):

    <the title>
    1. <first scene's name>
    2. ...
    <"Dòng khảo sát", videos.pinned_survey>

The title and the list are made from the video's title scene and content scenes as they are now, every time the
comment is shown, copied or posted, so editing, adding, deleting or reordering a scene changes it with no AI call.
A scene's name is the first line of its on-screen text with any number the script put before it dropped, and the
list is numbered again from 1, so a name that already says "1." is not numbered twice. A part that is empty is
left out, never left as a blank line.

web/src/lib/pinned.ts builds the same text for the live preview; keep the two in step.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import DEFAULT_PINNED_SURVEY, AffiliateProduct, Scene, Video, VideoAffiliateProduct
from .script_rules import Issue

DEFAULT_SURVEY = DEFAULT_PINNED_SURVEY
MAX_LENGTH = 1500

_SPACES = re.compile(r"\s+")
# A number the script put before a scene's name: "1. ", "2) ", "3 - ", "#4: ", "Cặp 5: ", "Số 6 – ". Only with a mark
# after it, so a name that starts with a number of its own ("5 loại rau") keeps it.
_INDEX = re.compile(r"^\s*(?:#|cặp\s*|số\s*)?\d+\s*[.):\-–—]\s*", re.IGNORECASE)
_LINK = re.compile(r"\blink\b", re.IGNORECASE)
# "7 món", "5 loại"...: a number in the title that says how many scenes the video should have.
_COUNTED = re.compile(
    r"(?<!\d)(\d{1,2})\s+(món|loại|cách|điều|thứ|mẹo|việc|bước|dấu hiệu|thói quen|sai lầm|lý do|lợi ích|kiểu|"
    r"thực phẩm|đồ|nguyên tắc|bài|cây|quả|rau|hạt|củ|cặp)\b",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    """Text as it reads: no *emphasis* marks, one Unicode form, single spaces."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", text.replace("*", ""))).strip()


def strip_index(name: str) -> str:
    """The name without the number the script put before it."""
    return _INDEX.sub("", name, count=1).strip()


@dataclass
class Source:
    title: str
    names: list[str] = field(default_factory=list)  # each content scene's name, in order, none empty
    product_names: list[str] = field(default_factory=list)


def build_source(title_text: str, scene_texts: list[str], product_names: list[str]) -> Source:
    """What the comment is made from: the title and each content scene's on-screen text, in order. A scene whose
    name is empty (no text, or only a number) is left out and the next one takes its number."""
    names = []
    for text in scene_texts:
        first = next((line for line in (normalize(line) for line in text.splitlines()) if line), "")
        name = strip_index(first)
        if name:
            names.append(name)
    return Source(normalize(title_text), names, [normalize(name) for name in product_names])


def items(source: Source) -> str:
    return "\n".join(f"{order}. {name}" for order, name in enumerate(source.names, start=1))


def render(survey: str, source: Source) -> str:
    """The comment: the title, the scenes one per line, then the survey line; an empty part is left out."""
    return "\n".join(part for part in (source.title, items(source), normalize(survey)) if part)


def validate(survey: str, source: Source, extra_comments: list[str]) -> list[Issue]:
    """Warnings about the comment as it renders now; none stops a render or a post. A title that counts more or fewer
    scenes than the video has is a warning of the scenes (shown at the top of the editor), the rest of the comment."""
    issues: list[Issue] = []
    text = render(survey, source)
    counted = _COUNTED.search(source.title)
    if counted and source.names and int(counted.group(1)) != len(source.names):
        issues.append(
            Issue(
                f"Tiêu đề ghi “{counted.group(0)}” nhưng video có {len(source.names)} cảnh nội dung: "
                "sửa tiêu đề cho khớp số cảnh",
                field="scenes",
            )
        )
    if not source.product_names and any(_LINK.search(one) for one in [text, *extra_comments]):
        issues.append(Issue("Bình luận nhắc tới “link” nhưng video chưa gắn sản phẩm nào", field="pinned_comment"))
    if len(text) > MAX_LENGTH:
        issues.append(
            Issue(f"Bình luận ghim dài {len(text)} ký tự, nên tối đa {MAX_LENGTH} ký tự", field="pinned_comment")
        )
    return issues


def survey_of_script(question: str) -> str:
    """A new script's survey line: the AI's question to viewers, or the default when it wrote none."""
    return normalize(question) or DEFAULT_SURVEY


def scenes_source(title: Scene | None, scenes: list[Scene], product_names: list[str], topic: str = "") -> Source:
    """The source from the video's title scene and content scenes (in their order), falling back to its topic."""
    title_text = title.text if title is not None and normalize(title.text) else topic
    return build_source(title_text, [scene.text for scene in scenes], product_names)


def product_names(db: DbSession, video_id: int) -> list[str]:
    """The names of the products attached to the video (only for the "link" warning)."""
    return list(
        db.scalars(
            select(AffiliateProduct.name)
            .join(VideoAffiliateProduct)
            .where(VideoAffiliateProduct.video_id == video_id)
            .order_by(AffiliateProduct.id)
        )
    )


def source_of(db: DbSession, video: Video) -> Source:
    rows = db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position, Scene.id)).all()
    title = next((scene for scene in rows if scene.is_title), None)
    return scenes_source(
        title, [scene for scene in rows if not scene.is_title], product_names(db, video.id), video.topic
    )


def text_of(db: DbSession, video: Video) -> str:
    """The pinned comment as it is now: what "Xem trước" shows, "Copy ghim" copies and the Page writes under a reel."""
    return render(video.pinned_survey, source_of(db, video))
