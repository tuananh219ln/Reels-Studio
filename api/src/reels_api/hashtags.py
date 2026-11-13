"""Hashtags belong in the video's Hashtag field, not in its caption. Scripts often end the caption with them anyway, and
the post then showed them twice (caption, then the field). These keep one copy.

TikTok gets its own caption: the caption text without its trailing Facebook hashtags, then the topic group's TikTok
set. Facebook's set must never reach TikTok: `#reels` is Facebook's word, and TikTok caps a caption at five tags."""

import re

# A hashtag word: "#" and letters or digits with at least one letter, so "#1" in "Món #1" is not one.
TAG = re.compile(r"#\w*[^\W\d_]\w*")

# The TikTok hashtag set of each topic group that posts to TikTok (the owner's decision, 2026-11-12): at most five
# tags, at most one topic tag. A group without one has no TikTok set of its own. Keyed by the group's name, as the
# team names groups everywhere else; if a second group starts on TikTok, this becomes a group setting.
TIKTOK_HASHTAGS = {
    "Ăn Lành Sống Khỏe – Sức khỏe": ["#suckhoe", "#songkhoe", "#anlanh", "#meosuckhoe"],
}


def _is_tag_line(line: str) -> bool:
    words = line.split()
    return bool(words) and all(TAG.fullmatch(word) for word in words)


def split_trailing(caption: str) -> tuple[str, list[str]]:
    """The caption without the lines of only hashtags at its end, and those hashtags in order."""
    lines = caption.rstrip().split("\n")
    tags: list[str] = []
    while lines and (_is_tag_line(lines[-1]) or not lines[-1].strip()):
        tags[:0] = lines.pop().split()
    return "\n".join(lines).rstrip(), tags


def merge(first: list[str], more: list[str]) -> list[str]:
    """`first`, then the tags of `more` it does not have yet; case is ignored, as Facebook does."""
    seen = {tag.lower() for tag in first}
    merged = list(first)
    for tag in more:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            merged.append(tag)
    return merged


def post_text(caption: str, hashtags: list[str]) -> str:
    """What is posted: the caption, then the hashtags it does not already hold."""
    present = {tag.lower() for tag in TAG.findall(caption)}
    extra = [tag for tag in merge([], hashtags) if tag.lower() not in present]
    return f"{caption}\n\n{' '.join(extra)}".strip()


_TRAILING_TAG = re.compile(r"#\w*[^\W\d_]\w*\s*$")


def strip_trailing_tags(text: str) -> str:
    """The text without the hashtags trailing it, whether on their own lines or inline at the end of the last line
    (a script's caption usually ends "...bác sĩ. #suckhoe #songkhoe ..."). A trailing "#1" stays: it is not a tag."""
    stripped = text.rstrip()
    while True:
        match = _TRAILING_TAG.search(stripped)
        if not match:
            return stripped
        stripped = stripped[: match.start()].rstrip()


def tiktok_caption(caption: str, topic_name: str | None) -> str:
    """The caption to copy or send to TikTok: the caption text without its trailing Facebook hashtags, then the
    topic group's TikTok set. The video's own hashtag field is never used here: it holds the Facebook set."""
    return post_text(strip_trailing_tags(caption), TIKTOK_HASHTAGS.get(topic_name or "", []))
