"""Hashtags belong in the video's Hashtag field, not in its caption. Scripts often end the caption with them anyway, and
the post then showed them twice (caption, then the field). These keep one copy."""

import re

# A hashtag word: "#" and letters or digits with at least one letter, so "#1" in "Món #1" is not one.
TAG = re.compile(r"#\w*[^\W\d_]\w*")


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
