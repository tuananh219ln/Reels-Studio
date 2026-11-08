"""A member's last choices (brief docs/specs/chu-thuong-ca-nhan-hoa, part B3): the Page and the topic group they last
picked, kept by account so the create, publish and queue forms start on them on any device."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import ApiError
from .models import Fanpage, KnowledgeTopic, Session, UserLastChoices
from .sessions import current_member

router = APIRouter(prefix="/api/me/last-choices")


class ChoicesBody(BaseModel):
    # Each is saved only when sent; the other stays as it was.
    fanpage_id: int | None = None
    knowledge_topic_id: int | None = None


def _payload(row: UserLastChoices | None) -> dict:
    return {
        "fanpage_id": row.fanpage_id if row else None,
        "knowledge_topic_id": row.knowledge_topic_id if row else None,
    }


@router.get("")
def read(session: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _payload(db.get(UserLastChoices, session.user_id))


@router.patch("")
def save(body: ChoicesBody, session: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    sent = body.model_fields_set
    if "fanpage_id" in sent and body.fanpage_id is not None and db.get(Fanpage, body.fanpage_id) is None:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Fanpage")
    if (
        "knowledge_topic_id" in sent
        and body.knowledge_topic_id is not None
        and db.get(KnowledgeTopic, body.knowledge_topic_id) is None
    ):
        raise ApiError(404, "knowledge_topic_not_found", "Không tìm thấy nhóm chủ đề")
    row = db.get(UserLastChoices, session.user_id)
    if row is None:
        row = UserLastChoices(user_id=session.user_id)
        db.add(row)
    if "fanpage_id" in sent:
        row.fanpage_id = body.fanpage_id
    if "knowledge_topic_id" in sent:
        row.knowledge_topic_id = body.knowledge_topic_id
    db.commit()
    return _payload(row)
