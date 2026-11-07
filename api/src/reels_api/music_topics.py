"""The topics a music track is tagged with: the groups of Kho kiến thức, by name, plus "chung" for any topic.

A track stores the names (music_tracks.topics), so renaming a group renames it on every track and deleting a group
takes it off them (rename_topic, drop_topic, called by the /knowledge routes). Tags from before this rule (the old
fixed list) stay on their tracks until a member edits them: a track may keep the tags it has, only new ones must be
groups.
"""

import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import knowledge
from .models import MusicTrack

GENERAL = "chung"


class TopicError(ValueError):
    """The message is shown to members."""


def names(db: DbSession) -> list[str]:
    """The topics to choose from, in the order of Kho kiến thức, then "chung"."""
    groups = [topic.name for topic in knowledge.all_topics(db)]
    return [*groups, *([] if GENERAL in groups else [GENERAL])]


def clean(db: DbSession, values: list[str], kept: list[str] | None = None) -> list[str]:
    """The chosen topics, each a group of Kho kiến thức or "chung" (or one the track already had, `kept`), in the
    order of `names`, the kept old ones after them."""
    chosen = list(dict.fromkeys(unicodedata.normalize("NFC", value).strip() for value in values))
    chosen = [value for value in chosen if value]
    if not chosen:
        raise TopicError("Chọn ít nhất một chủ đề")
    offered = names(db)
    allowed = {*offered, *(kept or [])}
    if not set(chosen) <= allowed:
        raise TopicError("Chủ đề không có trong Kho kiến thức")
    return [name for name in offered if name in chosen] + [name for name in chosen if name not in offered]


def _tracks_with(db: DbSession, name: str) -> list[MusicTrack]:
    return list(db.scalars(select(MusicTrack).where(MusicTrack.topics.contains([name]))))


def rename_topic(db: DbSession, old: str, new: str) -> None:
    """A group renamed in Kho kiến thức: its tracks carry the new name. The caller commits."""
    if old == new:
        return
    for track in _tracks_with(db, old):
        track.topics = list(dict.fromkeys(new if name == old else name for name in track.topics))


def drop_topic(db: DbSession, name: str) -> None:
    """A group deleted from Kho kiến thức: its tracks lose the tag, and one left with none becomes "chung". The caller
    commits."""
    for track in _tracks_with(db, name):
        track.topics = [topic for topic in track.topics if topic != name] or [GENERAL]
