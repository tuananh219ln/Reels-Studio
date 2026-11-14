"""The pinned comment as a template ("Bình luận ghim tự đồng bộ", decisions 2026-11-14-pinned-comment-template).

`videos.pinned_comment` holds the template a member edits; `{title}`, `{items}`... in it are filled from the video's
title and scenes as they are now, every time it is shown, copied or posted, so editing, adding, deleting or
reordering a scene changes the comment with no AI call and nothing to keep in sync. A template with no variable is
plain text and renders as itself, which is how every comment written before this reads.

web/src/lib/pinned.ts renders the same way for the live preview while a member types; keep the two in step.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import AffiliateProduct, Scene, Video, VideoAffiliateProduct
from .script_rules import Issue

# What a template may name, each filled from the video at render time.
VARIABLES = ("title", "hook", "count", "items", "item_names", "products")
# The variables that list the scenes: a template without one no longer follows them.
ITEM_VARIABLES = ("items", "item_names")
# The template a newly written script gets: the title, the scenes one per line, then the AI's own comment.
DEFAULT_TEMPLATE = "{title}\n{items}"
MAX_LENGTH = 1500

_VARIABLE = re.compile(r"\{(\w+)\}")
_SPACES = re.compile(r"\s+")
_BLANK_LINES = re.compile(r"\n{3,}")
_NUMBERED = re.compile(r"^\s*(\d+)\s*[.)]\s*(.+)$")
_LINK = re.compile(r"\blink\b", re.IGNORECASE)
# "7 món", "5 loại"...: a number in the title that says how many scenes the video should have.
_COUNTED = re.compile(
    r"(?<!\d)(\d{1,2})\s+(món|loại|cách|điều|thứ|mẹo|việc|bước|dấu hiệu|thói quen|sai lầm|lý do|lợi ích|kiểu|"
    r"thực phẩm|đồ|nguyên tắc|bài|cây|quả|rau|hạt|củ)\b",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    """Text as it reads: no *emphasis* marks, one Unicode form, single spaces."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", text.replace("*", ""))).strip()


@dataclass
class Item:
    order: int
    name: str  # the scene text's first line
    benefit: str  # its other lines
    voice: str  # its narration, or its text when it has none


@dataclass
class Source:
    title: str
    hook: str
    items: list[Item] = field(default_factory=list)
    product_names: list[str] = field(default_factory=list)


def build_source(title_text: str, title_voice: str, scenes: list[tuple[str, str]], product_names: list[str]) -> Source:
    """What the comment is made from: the title, the title scene's narration, and each content scene, in order, as
    (on-screen text, narration). Photos, seconds, keywords and the like are not part of it."""
    items: list[Item] = []
    for text, voice in scenes:
        lines = [line for line in (normalize(line) for line in text.splitlines()) if line]
        if not lines:
            continue
        items.append(Item(len(items) + 1, lines[0], " ".join(lines[1:]), normalize(voice) or " ".join(lines)))
    title = normalize(title_text)
    return Source(title, normalize(title_voice) or title, items, [normalize(name) for name in product_names])


def item_line(item: Item) -> str:
    return f"{item.order}. {item.name}" + (f" – {item.benefit}" if item.benefit else "")


def render(template: str, source: Source) -> str:
    """The template with its variables filled; an unknown `{name}` stays as typed."""
    values = {
        "title": source.title,
        "hook": source.hook,
        "count": str(len(source.items)),
        "items": "\n".join(item_line(item) for item in source.items),
        "item_names": ", ".join(item.name for item in source.items),
        "products": "\n".join(source.product_names),
    }
    filled = _VARIABLE.sub(lambda match: values.get(match.group(1), match.group(0)), template)
    return _BLANK_LINES.sub("\n\n", filled).strip()


def follows_scenes(template: str) -> bool:
    return any(match.group(1) in ITEM_VARIABLES for match in _VARIABLE.finditer(template))


def default_template(comment: str) -> str:
    """A new script's template: the title and the scenes, then the comment the AI wrote (its question to viewers)."""
    comment = comment.strip()
    return f"{DEFAULT_TEMPLATE}\n{comment}" if comment else DEFAULT_TEMPLATE


def _key(text: str) -> str:
    return normalize(text).casefold()


def validate(template: str, source: Source, extra_comments: list[str]) -> list[Issue]:
    """Warnings about the comment as it renders now; none stops a render or a post. A title that counts more or fewer
    scenes than the video has is a warning of the scenes (shown at the top of the editor), the rest of the comment."""
    issues: list[Issue] = []

    def warn(message: str, field: str = "pinned_comment") -> None:
        issues.append(Issue(message, field=field))

    text = render(template, source)
    if not follows_scenes(template):
        # Typed by hand: a numbered list in it has to match the scenes, which no longer update it.
        listed = [normalize(match.group(2)) for match in map(_NUMBERED.match, text.splitlines()) if match]
        if listed:
            names = [item.name for item in source.items]
            known = {_key(name) for name in names}
            for line in listed:
                if not any(_key(line).startswith(name) for name in known):
                    warn(f"Bình luận ghim có dòng “{line}” không khớp cảnh nào")
            folded = _key(text)
            for item in source.items:
                if _key(item.name) not in folded:
                    warn(f"Bình luận ghim thiếu cảnh {item.order}: “{item.name}”")
            found = [name for name in names if _key(name) in folded]
            positions = [folded.find(_key(name)) for name in found]
            if positions != sorted(positions):
                warn("Thứ tự các món trong bình luận ghim khác thứ tự cảnh")
    counted = _COUNTED.search(source.title)
    if counted and source.items and int(counted.group(1)) != len(source.items):
        warn(
            f"Tiêu đề ghi “{counted.group(0)}” nhưng video có {len(source.items)} cảnh nội dung: "
            "sửa tiêu đề cho khớp số cảnh",
            "scenes",
        )
    if not source.product_names and any(_LINK.search(one) for one in [text, *extra_comments]):
        warn("Bình luận nhắc tới “link” nhưng video chưa gắn sản phẩm nào")
    if len(text) > MAX_LENGTH:
        warn(f"Bình luận ghim dài {len(text)} ký tự, nên tối đa {MAX_LENGTH} ký tự")
    return issues


def scenes_source(title: Scene | None, scenes: list[Scene], product_names: list[str], topic: str = "") -> Source:
    """The source from the video's title scene and content scenes (in their order), falling back to its topic."""
    title_text = title.text if title is not None and normalize(title.text) else topic
    return build_source(
        title_text,
        title.voice_text if title is not None else "",
        [(scene.text, scene.voice_text) for scene in scenes],
        product_names,
    )


def product_names(db: DbSession, video_id: int) -> list[str]:
    """The names of the products attached to the video, in the order their links follow the comment."""
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
    """The pinned comment as it is now: what "Copy ghim" copies and the Page writes under a reel."""
    return render(video.pinned_comment, source_of(db, video))
