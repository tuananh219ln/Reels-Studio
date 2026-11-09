"""Only the member who made a thing deletes it (part 4 of docs/specs/per-user-settings-ownership): another member is
refused with 403, whoever they are; seeing and using it stay shared. A thing whose maker is unknown is deleted by
nobody."""

from .errors import ApiError


def ensure_owner(owner_id: int | None, user_id: int, what: str) -> None:
    """Refuses the deletion unless `user_id` made the thing; `what` names it ("video này", "mẫu này"...)."""
    if owner_id is None or owner_id != user_id:
        raise ApiError(403, "not_owner", f"Chỉ người tạo {what} mới xoá được")


def ensure_none_of_others(counts: dict[str, int], what: str) -> None:
    """Refuses deleting a thing that holds things teammates made (`counts`: "video" → how many), naming them."""
    held = [f"{count} {name}" for name, count in counts.items() if count]
    if held:
        raise ApiError(
            409,
            "holds_others_work",
            f"{what} còn " + ", ".join(held) + " của thành viên khác nên không xoá được, để khỏi xoá lây đồ của họ",
        )
