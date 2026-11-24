"""The "Tài liệu" tab of a topic group on /knowledge: its Markdown documents. Anyone reads; writing follows the group's
"Cho cả đội sửa" like the rest of the group (ownership.ensure_group_editor)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import topic_docs
from .db import get_db
from .errors import ApiError
from .models import KnowledgeTopic, Session, TopicDoc
from .ownership import ensure_group_editor
from .sessions import current_member, now

router = APIRouter(prefix="/api/topic-docs")


class DocBody(BaseModel):
    section: str
    name: str
    body: str = ""
    pinned: bool = False


class DocPatchBody(BaseModel):
    section: str | None = None
    name: str | None = None
    body: str | None = None
    pinned: bool | None = None


def _topic(db: DbSession, topic_id: int) -> KnowledgeTopic:
    topic = db.get(KnowledgeTopic, topic_id)
    if topic is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    return topic


def _doc(db: DbSession, doc_id: int) -> TopicDoc:
    doc = db.get(TopicDoc, doc_id)
    if doc is None:
        raise ApiError(404, "doc_not_found", "Không tìm thấy tài liệu")
    return doc


def _unique(db: DbSession, topic_id: int, name: str, own_id: int | None = None) -> None:
    taken = db.scalar(select(TopicDoc.id).where(TopicDoc.knowledge_topic_id == topic_id, TopicDoc.name == name))
    if taken is not None and taken != own_id:
        raise ApiError(409, "doc_exists", f"Nhóm đã có tài liệu “{name}”")


@router.get("")
def list_docs(
    topic_id: int,
    q: str = "",
    section: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    _topic(db, topic_id)
    docs = topic_docs.listing(db, topic_id, topic_docs.clean_section(section) if section else None, q)
    return {
        "sections": [{"key": key, "label": label} for key, label in topic_docs.SECTIONS.items()],
        "docs": [topic_docs.payload(db, doc) for doc in docs],
    }


@router.get("/{doc_id}")
def get_doc(doc_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return topic_docs.payload(db, _doc(db, doc_id), with_body=True)


@router.post("", status_code=201)
def create_doc(
    topic_id: int, body: DocBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    topic = _topic(db, topic_id)
    ensure_group_editor(db, topic, me.user_id)
    name = topic_docs.clean_name(body.name)
    _unique(db, topic_id, name)
    doc = TopicDoc(
        knowledge_topic_id=topic_id,
        section=topic_docs.clean_section(body.section),
        name=name,
        body=topic_docs.clean_body(body.body),
        pinned=body.pinned,
        created_by_id=me.user_id,
        updated_by_id=me.user_id,
        updated_at=now(),
    )
    db.add(doc)
    db.commit()
    return topic_docs.payload(db, doc, with_body=True)


@router.patch("/{doc_id}")
def patch_doc(
    doc_id: int, body: DocPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    doc = _doc(db, doc_id)
    ensure_group_editor(db, _topic(db, doc.knowledge_topic_id), me.user_id)
    if body.section is not None:
        doc.section = topic_docs.clean_section(body.section)
    if body.name is not None:
        name = topic_docs.clean_name(body.name)
        _unique(db, doc.knowledge_topic_id, name, doc.id)
        doc.name = name
    if body.body is not None:
        doc.body = topic_docs.clean_body(body.body)
    if body.pinned is not None:
        doc.pinned = body.pinned
    doc.updated_by_id, doc.updated_at = me.user_id, now()
    db.commit()
    return topic_docs.payload(db, doc, with_body=True)


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    doc = _doc(db, doc_id)
    ensure_group_editor(db, _topic(db, doc.knowledge_topic_id), me.user_id)
    db.delete(doc)
    db.commit()
    return {"deleted": doc_id}
