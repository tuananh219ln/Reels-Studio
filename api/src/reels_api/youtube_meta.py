"""A topic group's "Mô tả YouTube" (`knowledge_topics.youtube_meta`, migration 0126): what its videos' YouTube
uploads carry instead of the Facebook caption (docs/decisions/2026-11-25-youtube-description.md).

The description and the tags are built when the upload starts, from the video's caption as it is then, so a caption
edited after the YouTube post was made still reaches YouTube. Facebook keeps its own caption and five hashtags.

- `hashtags`: the group's YouTube set, written in the description after the CTA and the disclaimer, and sent as the
  first tags.
- `keywords`: sent as tags only, after the hashtags, never in the description (a list of keywords there is "keyword stuffing" to YouTube).
- `cta`: the Subscribe line; `{channel}` is the name of the channel the video goes to.
- `disclaimer`: the full disclaimer, or "" for none (the Threads group has none).

A group with nothing set uploads what it did before: the caption and the video's own (Facebook) hashtags.
"""

from . import hashtags

FIELDS = ("hashtags", "keywords", "cta", "disclaimer")
CHANNEL = "{channel}"
MAX_HASHTAGS = 20
MAX_KEYWORDS = 40
MAX_WORD = 100
MAX_CTA = 500
MAX_DISCLAIMER = 2000
# The hashtags written in the description: YouTube ignores every hashtag of a description that has more than 60.
DESCRIPTION_HASHTAGS = 15
MAX_DESCRIPTION = 5000  # youtube_upload.MAX_DESCRIPTION
ELLIPSIS = "…"


class MetaError(ValueError):
    pass


def empty() -> dict:
    return {"hashtags": [], "keywords": [], "cta": "", "disclaimer": ""}


def of(stored: dict | None) -> dict:
    """The group's settings, every field present."""
    meta = empty()
    for field in FIELDS:
        if stored and stored.get(field):
            meta[field] = stored[field]
    return meta


def is_set(meta: dict | None) -> bool:
    return any(of(meta).values())


def _text(value: object, limit: int, label: str) -> str:
    if not isinstance(value, str):
        raise MetaError(f"{label} phải là chữ")
    text = value.replace("\r\n", "\n").strip()
    if len(text) > limit:
        raise MetaError(f"{label} dài quá {limit} ký tự")
    return text


def _words(value: object, limit: int, label: str) -> list[str]:
    if isinstance(value, str):
        value = value.replace("\n", ",").split(",")
    if not isinstance(value, list):
        raise MetaError(f"{label} phải là danh sách")
    words = [_text(word, MAX_WORD, label) for word in value]
    kept = hashtags.merge([], [word for word in words if word])
    if len(kept) > limit:
        raise MetaError(f"{label} tối đa {limit} mục")
    return kept


def clean(value: dict | None) -> dict | None:
    """What is saved from a form or a tool: every field checked; nothing set saves None (the group uses the old way).
    Hashtags may be sent with or without `#` and separated by spaces or commas; each must be a single hashtag word."""
    if not value:
        return None
    unknown = set(value) - set(FIELDS)
    if unknown:
        raise MetaError(f"Không có mục {', '.join(sorted(unknown))} trong Mô tả YouTube")
    meta = of(None)
    raw_tags = value.get("hashtags") or []
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.replace(",", " ").split()
    tags = []
    for word in _words(raw_tags, MAX_HASHTAGS, "Hashtag YouTube"):
        tag = word if word.startswith("#") else f"#{word}"
        if not hashtags.TAG.fullmatch(tag):
            raise MetaError(f"Hashtag không hợp lệ: {word}")
        tags.append(tag)
    meta["hashtags"] = hashtags.merge([], tags)
    meta["keywords"] = _words(value.get("keywords") or [], MAX_KEYWORDS, "Từ khóa YouTube")
    meta["cta"] = _text(value.get("cta") or "", MAX_CTA, "Câu kêu gọi đăng ký")
    meta["disclaimer"] = _text(value.get("disclaimer") or "", MAX_DISCLAIMER, "Lưu ý (disclaimer)")
    return meta if is_set(meta) else None


def description(caption: str, video_hashtags: list[str], stored: dict | None, channel_name: str | None) -> str:
    """The YouTube description of a video of the group: the caption without its trailing (Facebook) hashtags, then the
    CTA, the disclaimer and the group's YouTube hashtags, a blank line between each. A caption too long for the
    5000 characters is shortened, never the blocks after it. Nothing set: the caption and the video's hashtags."""
    if not is_set(stored):
        return hashtags.post_text(caption, video_hashtags)
    meta = of(stored)
    cta = meta["cta"]
    if CHANNEL in cta:
        cta = cta.replace(CHANNEL, channel_name.strip()) if channel_name and channel_name.strip() else ""
    tags = meta["hashtags"] or hashtags.merge([], video_hashtags)
    tail = [block.strip() for block in (cta, meta["disclaimer"], " ".join(tags[:DESCRIPTION_HASHTAGS]))]
    tail_text = "\n\n".join(block for block in tail if block)
    text = hashtags.strip_trailing_tags(caption)
    room = MAX_DESCRIPTION - len(tail_text) - (2 if tail_text else 0)
    if len(text) > room:
        text = text[: max(room - len(ELLIPSIS), 0)].rstrip() + ELLIPSIS
    return "\n\n".join(block for block in (text, tail_text) if block)


def tags(video_hashtags: list[str], stored: dict | None) -> list[str]:
    """The tags of the upload: the group's YouTube hashtags (or the video's own when it has none), then its keywords,
    cleaned and cut to YouTube's 500 characters from the end (hashtags.youtube_tags)."""
    meta = of(stored)
    return hashtags.youtube_tags((meta["hashtags"] or list(video_hashtags)) + meta["keywords"])
