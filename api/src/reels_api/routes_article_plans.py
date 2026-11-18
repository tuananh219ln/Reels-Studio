"""A Page's 30-day plan of article scripts (article_plans.py): read by the whole team, changed by the Page's owner
only, as the Page's queue and its posts are."""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import article_plans, articles, fanpages, slot_comments
from .db import get_db
from .errors import ApiError
from .models import ARTICLE_KINDS, ArticlePlan, ArticlePlanSlot, Fanpage, KnowledgeTopic, Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/article-plans")


class SettingsBody(BaseModel):
    start_date: date | None = None
    per_day: int = 3
    post_times: list[str] = article_plans.DEFAULT_TIMES
    topic_group_ids: list[int] = []
    kind_mix: dict[str, int] = {}
    tone: str = ""
    audience: str = ""


class SlotBody(BaseModel):
    hook: str | None = None
    body: str | None = None
    cta: str | None = None
    hashtags: list[str] | None = None
    image_brief: str | None = None
    image_urls: list[str] | None = None
    kind: str | None = None
    knowledge_topic_id: int | None = None
    skipped: bool | None = None
    # Where it goes: both set for a day and slot, both null for the Backlog; left out, it stays.
    day: int | None = None
    slot: int | None = None


class IdsBody(BaseModel):
    ids: list[int]


class CommentsBody(BaseModel):
    pinned_comments: list[dict]
    pin_index: int = 0


class GenerateCommentsBody(BaseModel):
    index: int | None = None  # one comment only (↻); left out, all five


class BulkCommentsBody(BaseModel):
    scope: str = "missing"
    ids: list[int] = []
    overwrite: bool = False


class ApplyBody(BaseModel):
    rows: list[dict]
    placement: str = "by_day_slot"
    conflict: str = "to_backlog"


def _page(db: DbSession, fanpage_id: int) -> Fanpage:
    page = db.get(Fanpage, fanpage_id)
    if page is None or not page.active:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Page (có thể đã ngừng dùng)")
    return page


def _owned(db: DbSession, fanpage_id: int, me: Session) -> tuple[Fanpage, ArticlePlan]:
    """The Page's plan, locked, for its owner; refused to anyone else and before "Thiết lập" made it."""
    page = _page(db, fanpage_id)
    _owner(page, me)
    plan = article_plans.plan_of(db, page.id, lock=True)
    if plan is None:
        raise ApiError(409, "no_article_plan", "Page chưa có kế hoạch: bấm Thiết lập trước")
    return page, plan


def _owner(page: Fanpage, me: Session) -> None:
    """Only the Page's owner changes its plan, as only they post to it."""
    if page.owner_id is None:
        raise ApiError(403, "not_page_owner", f"Page “{page.name}” chưa có chủ: hãy bấm “Nhận Page” ở Quản lý kênh")
    if page.owner_id != me.user_id:
        owner = page.owner.name if page.owner else "chủ Page"
        raise ApiError(403, "not_page_owner", f"Chỉ chủ Page “{page.name}” ({owner}) mới sửa được kế hoạch này")


def _payload(db: DbSession, page: Fanpage, me: Session) -> dict:
    plan = article_plans.plan_of(db, page.id)
    data = article_plans.payload(db, page, plan, me.user_id)
    following = article_plans.next_unused(db, plan) if plan else None
    data["next_slot_id"] = following.id if following else None
    return data


def _saved(db: DbSession, page: Fanpage, me: Session, **extra: object) -> dict:
    db.commit()
    return {**_payload(db, page, me), **extra}


def _slot(db: DbSession, slot_id: int, me: Session) -> tuple[Fanpage, ArticlePlan, ArticlePlanSlot]:
    slot = db.get(ArticlePlanSlot, slot_id)
    if slot is None:
        raise ApiError(404, "plan_slot_not_found", "Không tìm thấy kịch bản (có thể đã bị xoá)")
    plan = db.get(ArticlePlan, slot.plan_id)
    page, plan = _owned(db, plan.fanpage_id, me)
    slot = db.scalar(select(ArticlePlanSlot).where(ArticlePlanSlot.id == slot_id).with_for_update())
    return page, plan, slot


def _text(value: str, limit: int, label: str) -> str:
    text = value.replace("\r\n", "\n").strip()
    if len(text) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return text


def _fill(db: DbSession, slot: ArticlePlanSlot, body: SlotBody) -> None:
    if body.hook is not None:
        slot.hook = _text(body.hook, article_plans.MAX_HOOK, "Câu mở")
        if not slot.hook:
            raise invalid("Hãy nhập câu mở (hook)")
    if body.body is not None:
        slot.body = _text(body.body, article_plans.MAX_BODY, "Nội dung")
    if body.cta is not None:
        slot.cta = _text(body.cta, article_plans.MAX_CTA, "Câu kêu gọi bình luận")
    if body.image_brief is not None:
        slot.image_brief = _text(body.image_brief, article_plans.MAX_BRIEF, "Gợi ý ảnh")
    if body.hashtags is not None:
        slot.hashtags = articles.clean_hashtags(body.hashtags)
    if body.image_urls is not None:
        urls = [url.strip() for url in body.image_urls if url.strip()]
        if len(urls) > article_plans.MAX_LINKS or any(not url.startswith(("http://", "https://")) for url in urls):
            raise invalid(f"Tối đa {article_plans.MAX_LINKS} link ảnh, mỗi link bắt đầu bằng http(s)://")
        slot.image_urls = urls
    fields = body.model_fields_set
    if "kind" in fields:
        if body.kind is not None and body.kind not in ARTICLE_KINDS:
            raise invalid("Dạng bài không hợp lệ")
        slot.kind = body.kind
    if "knowledge_topic_id" in fields:
        if body.knowledge_topic_id is not None and db.get(KnowledgeTopic, body.knowledge_topic_id) is None:
            raise invalid("Không tìm thấy nhóm chủ đề")
        slot.knowledge_topic_id = body.knowledge_topic_id
    if body.skipped is not None:
        if body.skipped and slot.article_id is not None:
            raise ApiError(409, "plan_slot_used", "Kịch bản đã có bài, không bỏ qua được")
        slot.skipped = body.skipped


@router.get("/pages")
def plan_pages(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """The Pages in use, the member's own first, and whether each has a plan."""
    planned = set(db.scalars(select(ArticlePlan.fanpage_id)))
    pages = fanpages.in_use(db)
    pages.sort(key=lambda page: page.owner_id != me.user_id)
    return [
        {"id": page.id, "name": page.name, "mine": page.owner_id == me.user_id, "has_plan": page.id in planned}
        for page in pages
    ]


@router.get("/import-template")
def import_template(format: str = "csv", me: Session = Depends(current_member), db: DbSession = Depends(get_db)):
    if format not in ("csv", "json"):
        raise invalid("Chỉ có file mẫu CSV hoặc JSON")
    group = db.scalar(select(KnowledgeTopic.name).order_by(KnowledgeTopic.id).limit(1)) or ""
    data, name, media_type = article_plans.template(format, group)
    return Response(data, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{fanpage_id}")
def get_plan(fanpage_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _payload(db, _page(db, fanpage_id), me)


@router.put("/{fanpage_id}/settings")
def save_settings(
    fanpage_id: int, body: SettingsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Thiết lập": made on the first save. Fewer posts a day moves the dropped slots' scripts to the Backlog."""
    page = _page(db, fanpage_id)
    _owner(page, me)
    if body.start_date is None:
        raise invalid("Chọn ngày bắt đầu để app biết hôm nay là ngày mấy của kế hoạch")
    plan = article_plans.plan_of(db, page.id, lock=True)
    if plan is None:
        plan = ArticlePlan(fanpage_id=page.id, created_by_id=me.user_id)
        db.add(plan)
    try:
        moved = article_plans.apply_settings(
            db,
            plan,
            body.start_date,
            body.per_day,
            body.post_times,
            body.topic_group_ids,
            body.kind_mix,
            body.tone,
            body.audience,
        )
    except ValueError as err:
        raise invalid(str(err)) from None
    plan.updated_by_id = me.user_id
    return _saved(db, page, me, moved_to_backlog=moved)


@router.post("/{fanpage_id}/slots", status_code=201)
def add_slot(
    fanpage_id: int, body: SlotBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """A script typed by hand, on an empty slot or in the Backlog."""
    page, plan = _owned(db, fanpage_id, me)
    slot = ArticlePlanSlot(plan_id=plan.id, hook="", source="manual", created_by_id=me.user_id)
    _fill(db, slot, body)
    if not slot.hook:
        raise invalid("Hãy nhập câu mở (hook)")
    if body.day is not None and article_plans.cell(db, plan.id, body.day, body.slot or 0) is not None:
        raise ApiError(409, "plan_slot_taken", "Ô này đã có kịch bản")
    if body.day is None and article_plans.backlog_count(db, plan.id) >= article_plans.MAX_BACKLOG:
        raise invalid(f"Backlog đã đủ {article_plans.MAX_BACKLOG} kịch bản")
    db.add(slot)
    db.flush()
    try:
        article_plans.move(db, plan, slot, body.day, body.slot)
    except ValueError as err:
        raise invalid(str(err)) from None
    return _saved(db, page, me)


@router.patch("/slots/{slot_id}")
def patch_slot(
    slot_id: int, body: SlotBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Sửa", "Bỏ qua", and dragging: to another slot (swapping with what is there) or to the Backlog."""
    page, plan, slot = _slot(db, slot_id, me)
    _fill(db, slot, body)
    if {"day", "slot"} & body.model_fields_set:
        try:
            article_plans.move(db, plan, slot, body.day, body.slot)
        except ValueError as err:
            raise invalid(str(err)) from None
    return _saved(db, page, me)


@router.post("/{fanpage_id}/slots/delete")
def delete_slots(
    fanpage_id: int, body: IdsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Xóa nhiều kịch bản": the chosen slots' and Backlog's scripts; one an article was made from stays."""
    page, plan = _owned(db, fanpage_id, me)
    deleted = kept = 0
    for slot in db.scalars(
        select(ArticlePlanSlot).where(ArticlePlanSlot.plan_id == plan.id, ArticlePlanSlot.id.in_(body.ids))
    ):
        if slot.article_id is not None:
            kept += 1
            continue
        db.delete(slot)
        deleted += 1
    return _saved(db, page, me, deleted=deleted, kept=kept)


@router.post("/{fanpage_id}/import")
def preview_import(
    fanpage_id: int,
    file: UploadFile = File(...),
    placement: str = Form("by_day_slot"),
    conflict: str = Form("to_backlog"),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """ "Nhập file JSON/CSV": the file's scripts checked and placed, shown before anything is written."""
    _, plan = _owned(db, fanpage_id, me)
    _modes(placement, conflict)
    data = file.file.read(article_plans.MAX_FILE_BYTES + 1)
    try:
        preview = article_plans.preview_file(db, plan, file.filename or "", data, placement, conflict)
    except article_plans.PlanFileError as err:
        raise invalid(str(err)) from None
    db.rollback()
    return {**preview, "file_name": file.filename}


@router.post("/{fanpage_id}/import/apply")
def apply_import(
    fanpage_id: int, body: ApplyBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Lưu kế hoạch": the previewed rows checked again, those without errors written; the Backlog is kept."""
    page, plan = _owned(db, fanpage_id, me)
    _modes(body.placement, body.conflict)
    if len(body.rows) > article_plans.MAX_ROWS:
        raise invalid(f"Tối đa {article_plans.MAX_ROWS} dòng")
    try:
        rows = article_plans.rows_from_payload(body.rows)
        article_plans.check_rows(db, plan, rows)
        report = article_plans.apply_rows(db, plan, rows, body.placement, body.conflict, me.user_id)
    except (TypeError, ValueError) as err:
        db.rollback()
        raise invalid(str(err)) from None
    return _saved(db, page, me, report=report)


def _modes(placement: str, conflict: str) -> None:
    if placement not in article_plans.PLACEMENTS or conflict not in article_plans.CONFLICTS:
        raise invalid("Cách xếp hoặc cách xử lý ô đã có kịch bản không hợp lệ")


# --- Bình luận ghim (slot_comments.py) ---


@router.put("/slots/{slot_id}/comments")
def save_comments(
    slot_id: int, body: CommentsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The comments a member typed, dragged into order or chose a pin for: marked as edited by hand, so a bulk run
    leaves them alone."""
    page, _, slot = _slot(db, slot_id, me)
    checked = slot_comments.check(body.pinned_comments, body.pin_index, slot.kind)
    if checked.errors:
        raise invalid("; ".join(checked.errors))
    slot_comments.set_comments(slot, checked, "manual", edited=True)
    return _saved(db, page, me, warnings=checked.warnings)


@router.post("/slots/{slot_id}/comments/generate")
def generate_comments(
    slot_id: int, body: GenerateCommentsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Tạo lại bằng AI" (all five) or ↻ (one): a job; the member asked for it, so a hand edit is replaced."""
    page, _, slot = _slot(db, slot_id, me)
    if body.index is not None and not 0 <= body.index < slot_comments.MAX_COMMENTS:
        raise invalid("Vị trí bình luận không hợp lệ")
    queued = slot_comments.queue(db, [slot], me.user_id, overwrite=True, index=body.index)
    return _saved(db, page, me, queued=queued)


@router.post("/{fanpage_id}/comments/bulk")
def bulk_comments(
    fanpage_id: int, body: BulkCommentsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Tạo bình luận ghim": a job per script in the chosen scope; scripts edited by hand are skipped unless
    "Ghi đè"."""
    page, plan = _owned(db, fanpage_id, me)
    if body.scope not in slot_comments.SCOPES:
        raise invalid("Phạm vi không hợp lệ")
    slots = slot_comments.scope_slots(db, plan, body.scope, body.ids)
    skipped = sum(1 for slot in slots if slot.comments_edited) if not body.overwrite else 0
    queued = slot_comments.queue(db, slots, me.user_id, overwrite=body.overwrite)
    return _saved(db, page, me, queued=queued, skipped_edited=skipped)


@router.get("/{fanpage_id}/comments/count")
def count_comments(
    fanpage_id: int,
    scope: str = "missing",
    ids: str = "",
    overwrite: bool = False,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """How many scripts a "Tạo bình luận ghim" run would write for, shown in its dialog before it starts."""
    page = _page(db, fanpage_id)
    plan = article_plans.plan_of(db, page.id)
    if plan is None or scope not in slot_comments.SCOPES:
        raise invalid("Phạm vi không hợp lệ")
    chosen = [int(part) for part in ids.split(",") if part.strip().isdigit()]
    slots = slot_comments.scope_slots(db, plan, scope, chosen)
    edited = sum(1 for slot in slots if slot.comments_edited)
    return {"total": len(slots), "edited": edited, "will_run": len(slots) - (0 if overwrite else edited)}
