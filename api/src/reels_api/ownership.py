"""Only the member who made a thing deletes it (part 4 of docs/specs/per-user-settings-ownership): another member is
refused with 403, whoever they are; seeing and using it stay shared. A thing whose maker is unknown is deleted by
nobody."""

from .errors import ApiError
from .models import Fanpage, Publication


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


def ensure_page_owner(page: Fanpage, user_id: int) -> None:
    """Only a Page's owner posts to it, as a post's commission is its Page's owner's (2026-11-09, option A). A Page
    with no owner is claimed first ("Nhận Page" on Quản lý Page)."""
    if page.owner_id is None:
        raise ApiError(
            403, "not_page_owner", f"Page “{page.name}” chưa có chủ: hãy bấm “Nhận Page” ở Quản lý Page rồi đăng"
        )
    if page.owner_id != user_id:
        owner = page.owner.name if page.owner else "chủ Page"
        raise ApiError(403, "not_page_owner", f"Chỉ chủ Page “{page.name}” ({owner}) mới đăng được lên Page này")


def ensure_can_take_down(db, post: Publication, user_id: int) -> None:
    """A post is taken down by whoever posted it, or by the owner of the Page it is on."""
    page = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
    if page is not None and page.owner_id is not None and page.owner_id == user_id:
        return
    ensure_owner(post.created_by_id, user_id, "bài đăng này")
