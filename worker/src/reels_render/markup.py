import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Run:
    text: str
    red: bool


class MarkupError(ValueError):
    pass


def normalize_text(text: str) -> str:
    """NFC first so combining marks from some editors become precomposed Vietnamese letters."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).upper())


def parse_scene_text(text: str) -> list[list[Run]]:
    """Split scene text into manual lines of runs; `*...*` marks red runs and may span lines."""
    text = normalize_text(text.replace("\r\n", "\n"))
    if not text.strip():
        raise MarkupError("chữ trống")
    if any(not line.strip() for line in text.split("\n")):
        raise MarkupError("có dòng trống (thừa xuống dòng \\n)")

    parts = text.split("*")
    if len(parts) % 2 == 0:
        raise MarkupError("dấu * không đóng cặp")
    if any(not part.strip() for part in parts[1::2]):
        raise MarkupError("có cặp ** rỗng")

    lines: list[list[Run]] = [[]]
    for index, part in enumerate(parts):
        for line_index, chunk in enumerate(part.split("\n")):
            if line_index:
                lines.append([])
            if chunk:
                lines[-1].append(Run(chunk, red=index % 2 == 1))
    return lines
