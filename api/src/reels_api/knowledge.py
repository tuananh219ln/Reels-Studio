"""The editable prompt and banned words on /knowledge; a missing row means the default from code."""

from functools import cache
from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from .models import Setting
from .script_rules import DEFAULT_BANNED_WORDS

SCRIPT_PROMPT = "script_prompt"
CLONE_PROMPT = "clone_prompt"
BANNED_WORDS = "banned_words"


def _prompt_file(name: str) -> str:
    return (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8").rstrip("\n")


@cache
def default_script_prompt() -> str:
    return _prompt_file("script_default.txt")


@cache
def default_clone_prompt() -> str:
    return _prompt_file("clone_default.txt")


def defaults() -> dict:
    return {
        SCRIPT_PROMPT: default_script_prompt(),
        CLONE_PROMPT: default_clone_prompt(),
        BANNED_WORDS: list(DEFAULT_BANNED_WORDS),
    }


def get(db: DbSession, key: str):
    row = db.get(Setting, key)
    return row.value if row is not None else defaults()[key]


def script_prompt(db: DbSession) -> str:
    return get(db, SCRIPT_PROMPT)


def clone_prompt(db: DbSession) -> str:
    return get(db, CLONE_PROMPT)


def banned_words(db: DbSession) -> list[str]:
    return get(db, BANNED_WORDS)


def put(db: DbSession, key: str, value, user_id: int) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value, updated_by_id=user_id))
    else:
        row.value = value
        row.updated_by_id = user_id
