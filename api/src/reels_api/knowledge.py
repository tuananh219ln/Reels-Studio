"""The knowledge topics on /knowledge and the default prompts that can be restored into them."""

from functools import cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import KnowledgeTopic, Video


def _prompt_file(name: str) -> str:
    return (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8").rstrip("\n")


@cache
def default_script_prompt() -> str:
    return _prompt_file("script_default.txt")


@cache
def default_clone_prompt() -> str:
    return _prompt_file("clone_default.txt")


@cache
def default_learn_prompt() -> str:
    return _prompt_file("learn_default.txt")


@cache
def default_analyze_prompt() -> str:
    return _prompt_file("analyze_default.txt")


def all_topics(db: DbSession) -> list[KnowledgeTopic]:
    return list(db.scalars(select(KnowledgeTopic).order_by(KnowledgeTopic.id)))


def topic_of(db: DbSession, video: Video) -> KnowledgeTopic | None:
    return db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None


def banned_words(db: DbSession, video: Video) -> list[str]:
    topic = topic_of(db, video)
    return topic.banned_words if topic else []
