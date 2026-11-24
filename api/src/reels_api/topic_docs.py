"""The documents of a topic group ("Tài liệu" on /knowledge, `list_docs` and `get_doc` on MCP): Markdown files of how a
group's Page is run. The copy in the app is the master (docs/decisions/2026-11-24-topic-docs.md); the daily job reads
its rules from here instead of having them pasted into its body, so they cannot drift apart."""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .errors import ApiError
from .models import TopicDoc, User

# The sections of the tab, in the order shown: key → label.
SECTIONS = {
    "job": "Job",
    "template": "Mẫu",
    "plan": "Kế hoạch",
    "prompt": "Prompt",
    "report": "Báo cáo",
}
MAX_NAME_LENGTH = 120
MAX_BODY_LENGTH = 200_000
_BAD_NAME = re.compile(r"[\\/\x00-\x1f]")


def clean_section(section: str) -> str:
    if section not in SECTIONS:
        raise ApiError(422, "invalid_section", "Mục phải là Job, Mẫu, Kế hoạch, Prompt hoặc Báo cáo")
    return section


def clean_name(name: str) -> str:
    """A file name: no slash, at most MAX_NAME_LENGTH characters, ending in ".md" (added when missing)."""
    name = " ".join(unicodedata.normalize("NFC", name).split())
    if not name or _BAD_NAME.search(name):
        raise ApiError(422, "invalid_name", "Tên tài liệu không được trống hoặc có dấu gạch chéo")
    if not name.lower().endswith(".md"):
        name += ".md"
    if len(name) > MAX_NAME_LENGTH:
        raise ApiError(422, "invalid_name", f"Tên tài liệu dài quá {MAX_NAME_LENGTH} ký tự")
    return name


def clean_body(body: str) -> str:
    if len(body) > MAX_BODY_LENGTH:
        raise ApiError(422, "doc_too_long", f"Tài liệu dài quá {MAX_BODY_LENGTH} ký tự")
    return body.replace("\r\n", "\n")


def search_key(text: str) -> str:
    """Text compared without accents or case: "mau chung" finds "Mẫu chung"."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return plain.replace("đ", "d").replace("Đ", "D").casefold()


def title_of(doc: TopicDoc) -> str:
    """The document's first Markdown heading, else its file name."""
    for line in doc.body.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            if heading:
                return heading
    return doc.name


def payload(db: DbSession, doc: TopicDoc, with_body: bool = False) -> dict:
    editor = db.get(User, doc.updated_by_id or doc.created_by_id) if (doc.updated_by_id or doc.created_by_id) else None
    return {
        "id": doc.id,
        "knowledge_topic_id": doc.knowledge_topic_id,
        "section": doc.section,
        "section_label": SECTIONS[doc.section],
        "name": doc.name,
        "title": title_of(doc),
        "pinned": doc.pinned,
        "size": len(doc.body),
        "updated_by": editor.name if editor else None,
        "updated_at": doc.updated_at.isoformat(),
        **({"body": doc.body} if with_body else {}),
    }


def listing(db: DbSession, topic_id: int, section: str | None = None, query: str = "") -> list[TopicDoc]:
    """The group's documents, pinned first, then by section and name; `query` keeps those whose name, title or text
    holds it (accents and case ignored)."""
    docs = list(db.scalars(select(TopicDoc).where(TopicDoc.knowledge_topic_id == topic_id)))
    if section:
        docs = [doc for doc in docs if doc.section == section]
    needle = search_key(query.strip())
    if needle:
        docs = [doc for doc in docs if needle in search_key(f"{doc.name}\n{doc.body}")]
    order = list(SECTIONS)
    return sorted(docs, key=lambda doc: (not doc.pinned, order.index(doc.section), doc.name.casefold()))


def find(db: DbSession, topic_id: int, doc_id: int | None = None, name: str | None = None) -> TopicDoc:
    """One document of the group, by id or by file name."""
    query = select(TopicDoc).where(TopicDoc.knowledge_topic_id == topic_id)
    if doc_id is not None:
        query = query.where(TopicDoc.id == doc_id)
    elif name:
        query = query.where(TopicDoc.name == clean_name(name))
    else:
        raise ApiError(422, "doc_missing", "Cần id hoặc tên tài liệu")
    doc = db.scalar(query)
    if doc is None:
        raise ApiError(404, "doc_not_found", "Không tìm thấy tài liệu")
    return doc
