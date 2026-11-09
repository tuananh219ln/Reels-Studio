"""Only the member who made a thing deletes it (part 4 of docs/specs/per-user-settings-ownership): another member is
refused with 403, whoever they are; seeing and using it stay shared. A thing whose maker is unknown is deleted by
nobody."""

from .errors import ApiError
from .models import KnowledgeTopic, User


def ensure_owner(owner_id: int | None, user_id: int, what: str, can: str = "xoá được") -> None:
    """Refuses the deletion (or what `can` says) unless `user_id` made the thing; `what` names it ("video này")."""
    if owner_id is None or owner_id != user_id:
        raise ApiError(403, "not_owner", f"Chỉ người tạo {what} mới {can}")


def ensure_none_of_others(counts: dict[str, int], what: str) -> None:
    """Refuses deleting a thing that holds things teammates made (`counts`: "video" → how many), naming them."""
    held = [f"{count} {name}" for name, count in counts.items() if count]
    if held:
        raise ApiError(
            409,
            "holds_others_work",
            f"{what} còn " + ", ".join(held) + " của thành viên khác nên không xoá được, để khỏi xoá lây đồ của họ",
        )


def ensure_group_editor(db, topic: KnowledgeTopic, user_id: int) -> None:
    """Editing a topic group and its plan: anyone while "Cho cả đội sửa" is on, else only the group's maker
    (2026-11-09). Using the group (videos, its ideas, reading its prompts and plan) is never refused here."""
    if topic.team_edit or topic.created_by_id == user_id:
        return
    maker = db.get(User, topic.created_by_id) if topic.created_by_id else None
    raise ApiError(
        403,
        "group_locked",
        f"Nhóm “{topic.name}” chỉ người tạo nhóm ({maker.name if maker else 'chưa có'}) được sửa: đã tắt “Cho cả đội sửa”",
    )
