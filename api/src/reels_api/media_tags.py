"""Tags of the "Kho tư liệu": what a photo or clip shows (a movement, a joint, a room, an opening or closing scene),
looked up by members on /media and by the MCP assistant (`list_media` with `tags`). Kept one way whatever was typed:
lowercase, Vietnamese without accents, words joined with "-" ("Xoay Cổ" is `xoay-co`), each once per item. Tags and
folders are independent: a folder says where an item is kept, its tags what it is
(docs/decisions/2026-11-11-media-tags.md)."""

import re
import unicodedata

MAX_TAG = 50
MAX_TAGS = 30


class TagError(ValueError):
    """A tag that is empty once cleaned, too long, or too many on one item: the message is shown as is."""


def plain(text: str) -> str:
    """Lowercase Vietnamese without accents ("Đi bộ" is "di bo")."""
    decomposed = unicodedata.normalize("NFD", text.replace("Đ", "D").replace("đ", "d"))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def clean_tag(raw: str) -> str:
    tag = re.sub(r"[^a-z0-9]+", "-", plain(raw or "")).strip("-")
    if not tag:
        raise TagError("Thẻ không được để trống")
    if len(tag) > MAX_TAG:
        raise TagError(f"Thẻ “{tag[:20]}…” dài quá {MAX_TAG} ký tự")
    return tag


def clean_tags(raw: list[str]) -> list[str]:
    """Each tag cleaned, in the order given, each once."""
    tags = list(dict.fromkeys(clean_tag(tag) for tag in raw))
    if len(tags) > MAX_TAGS:
        raise TagError(f"Mỗi tư liệu tối đa {MAX_TAGS} thẻ")
    return tags


def split_tags(text: str | None) -> list[str]:
    """Tags written in one line, separated by commas ("xoay-co, sofa"), as a form or a query string sends them."""
    return clean_tags([part for part in (text or "").split(",") if part.strip()])
