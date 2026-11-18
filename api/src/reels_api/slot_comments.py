"""'Bình luận ghim' of an article plan's scripts (decisions 2026-11-18, "pinned comments").

Each script holds up to 5 comments about its dish, one of them marked to be pinned. They come from a file (CSV or
JSON, checked by `check`), from "Tạo bình luận ghim" (an AI job per script, `run_job`) or from a member's hand. When
the article made from the script is live, the worker copies the comments into `post_comments` and writes them under the
post as the Page, the one to pin first, the others 20–40 seconds apart (`run_due`).

The Graph API has no call to pin a comment, so a pinned one is left "Chờ ghim tay" for a member to pin on Facebook and
tick "Đã ghim". Like the affiliate comment (post_comments.py) this is not a job and never sleeps: each comment has the
time it is due, and the worker's round writes the ones that are.
"""

import json
import logging
import random
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import articles, facebook, fanpages
from .claude import ClaudeError, ScriptOutputError, json_object
from .facebook import FacebookError
from .models import (
    Article,
    ArticlePlan,
    ArticlePlanSlot,
    Fanpage,
    Job,
    PostComment,
    Publication,
)
from .sessions import now
from .videos import live_at

log = logging.getLogger("reels_api.slot_comments")

MAX_COMMENTS = 5
MIN_TEXT, MAX_TEXT = 20, 1000
MAX_TYPE = 32
JOB_KIND = "slot_comments"
SOURCES = ("import", "ai", "manual")
# Two sets of labels, in the order they are written: for a dish worth eating and for a warning.
TYPES_FOOD = ("cong_dung", "cach_lam", "luu_y", "nen_dung", "han_che")
TYPES_WARNING = ("tac_hai", "thay_the", "luu_y", "can_tranh", "an_it_hai")
TYPE_LABELS = {
    "cong_dung": "Công dụng",
    "cach_lam": "Cách làm",
    "luu_y": "Lưu ý",
    "nen_dung": "Ai nên dùng",
    "han_che": "Ai nên hạn chế",
    "tac_hai": "Tác hại",
    "thay_the": "Thay thế",
    "can_tranh": "Ai cần tránh",
    "an_it_hai": "Ăn sao cho đỡ hại",
}
# What a comment may not promise: the AI writes it again, and a member's text is warned about.
SENSITIVE = ("chữa khỏi", "điều trị dứt điểm", "thay thuốc", "đặc trị", "khắc tinh", "diệt tế bào ung thư")
AI_TRIES = 3  # the first answer and two more when it is unusable (spec 6.3)

# Writing under the post (spec 7.1): the first comment 30–60 s after the post is live, the others 20–40 s apart.
FIRST_DELAY = (30, 60)
GAP = (20, 40)
RETRY_MINUTES = (1, 3, 10)  # after the 1st, 2nd and 3rd failed attempt that may pass
BATCH = 3
# A post that went live longer ago than this gets no comments made for it (a script filled in afterwards).
START_WITHIN = timedelta(hours=24)

SCOPES = ("missing", "selected", "unposted")


def type_set(kind: str | None) -> tuple[str, ...]:
    return TYPES_WARNING if kind == "canh_bao" else TYPES_FOOD


def _plain(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def sensitive_hits(text: str) -> list[str]:
    haystack = _plain(text)
    return [word for word in SENSITIVE if word in haystack]


@dataclass
class Checked:
    """Comments as saved: `errors` stop them, `warnings` do not (spec 4.5)."""

    items: list[dict] = field(default_factory=list)
    pin_index: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check(raw: object, pin_index: object = 0, kind: str | None = None, keep_places: bool = False) -> Checked:
    """Checks a script's comments. `raw` is a list of {"type", "text"}; with `keep_places` an empty text stays as a
    hole (a CSV file's empty cell) so `pin_index` still points at the column it was written for, and is then left out."""
    result = Checked()
    if raw is None or raw == []:
        return result
    if not isinstance(raw, list):
        result.errors.append("pinned_comments phải là một danh sách")
        return result
    if len(raw) > MAX_COMMENTS:
        result.errors.append(f"Tối đa {MAX_COMMENTS} bình luận")
        return result
    known = set(TYPES_FOOD) | set(TYPES_WARNING)
    places: list[int] = []
    for place, item in enumerate(raw):
        if not isinstance(item, dict):
            result.errors.append(f"Bình luận {place + 1} phải có dạng {{type, text}}")
            continue
        text = item.get("text")
        text = unicodedata.normalize("NFC", text).strip() if isinstance(text, str) else ""
        if not text and keep_places:
            continue
        kind_name = item.get("type")
        kind_name = kind_name.strip() if isinstance(kind_name, str) else ""
        if not text:
            result.errors.append(f"Bình luận {place + 1} trống")
        elif len(text) > MAX_TEXT:
            result.errors.append(f"Bình luận {place + 1} dài quá {MAX_TEXT} ký tự")
        elif len(text) < MIN_TEXT:
            result.errors.append(f"Bình luận {place + 1} ngắn quá (cần {MIN_TEXT}–{MAX_TEXT} ký tự)")
        if kind_name and (kind_name not in known or len(kind_name) > MAX_TYPE):
            result.warnings.append(f"Bình luận {place + 1}: nhãn “{kind_name[:MAX_TYPE]}” không thuộc 2 bộ nhãn")
        for word in sensitive_hits(text):
            result.warnings.append(f"Bình luận {place + 1} có từ nhạy cảm: “{word}”")
        result.items.append({"type": kind_name or None, "text": text})
        places.append(place)
    if result.errors:
        return result
    wanted = pin_index if isinstance(pin_index, int) and not isinstance(pin_index, bool) else 0
    if not result.items:
        return result
    if keep_places:
        # The column the pin was written for, counted among the comments that are left.
        result.pin_index = places.index(wanted) if wanted in places else 0
        if wanted not in places:
            result.warnings.append("pin_index trỏ vào ô trống, đã đưa về bình luận đầu")
    else:
        result.pin_index = wanted if 0 <= wanted < len(result.items) else 0
        if result.pin_index != wanted:
            result.warnings.append(f"pin_index phải từ 0 đến {len(result.items) - 1}, đã đưa về 0")
    if len(result.items) < MAX_COMMENTS:
        result.warnings.append(f"Thiếu {len(result.items)}/{MAX_COMMENTS}")
    return result


def stored(items: list[dict]) -> list[dict]:
    """The comments as kept on a script: a type that is None is left out."""
    return [
        {"type": item["type"], "text": item["text"]} if item.get("type") else {"text": item["text"]} for item in items
    ]


def comments_of(slot: ArticlePlanSlot) -> list[dict]:
    return [item for item in slot.pinned_comments or [] if isinstance(item, dict) and item.get("text")]


def pin_of(slot: ArticlePlanSlot) -> int:
    count = len(comments_of(slot))
    return slot.pin_index if 0 <= slot.pin_index < count else 0


def set_comments(slot: ArticlePlanSlot, checked: Checked, source: str, edited: bool) -> None:
    slot.pinned_comments, slot.pin_index = stored(checked.items), checked.pin_index
    slot.comments_source, slot.comments_edited, slot.comments_updated_at = source, edited, now()


def label_of(slot_comments: list[dict]) -> str:
    return f"{len(slot_comments)}/{MAX_COMMENTS}"


# --- From a file ---


def from_record(record: dict) -> tuple[Checked, list[dict]]:
    """A file's comments: JSON's `pinned_comments` and `pin_index`, or CSV's `cmt_1..cmt_5`, `cmt_types` and
    `pin_index`. Returns the check (made without the kind: the file is only warned about a label outside the sets) and
    the comments as read, so a preview can show them."""
    raw = record.get("pinned_comments")
    pin = record.get("pin_index")
    csv_texts = [record.get(f"cmt_{n}") for n in range(1, MAX_COMMENTS + 1)]
    if raw in (None, "") and any(str(text or "").strip() for text in csv_texts):
        kinds = str(record.get("cmt_types") or "").split("|") if str(record.get("cmt_types") or "").strip() else []
        raw = [
            {"type": kinds[place].strip() if place < len(kinds) else "", "text": str(text or "")}
            for place, text in enumerate(csv_texts)
        ]
        return _checked_pin(raw, pin, keep_places=True), raw
    if isinstance(raw, str) and raw.strip():
        # JSON written inside a CSV cell.
        try:
            raw = json.loads(raw)
        except ValueError:
            return Checked(errors=["pinned_comments không đọc được"]), []
    return _checked_pin(raw, pin, keep_places=False), raw if isinstance(raw, list) else []


def _checked_pin(raw: object, pin: object, keep_places: bool) -> Checked:
    if isinstance(pin, str):
        pin = pin.strip()
        pin = int(pin) if pin.lstrip("-").isdigit() else 0
    if isinstance(pin, float) and pin.is_integer():
        pin = int(pin)
    return check(raw, pin if isinstance(pin, int) else 0, keep_places=keep_places)


# --- The AI ---


def build_prompt(
    page_name: str,
    audience: str,
    title: str,
    kind: str | None,
    caption: str,
    only: int | None = None,
    current: list[dict] | None = None,
) -> str:
    labels = type_set(kind)
    head = (
        f'Bạn viết bình luận cho Page "{page_name}" (đối tượng {audience or "người Việt trung niên"}).\n'
        "Bài viết:\n"
        f"- Tiêu đề: {title}\n"
        f"- Loại bài: {articles.KIND_LABELS.get(kind or '', '')}\n"
        f"- Caption: {caption}\n\n"
    )
    if only is None:
        ask = f"Viết ĐÚNG {MAX_COMMENTS} bình luận tiếng Việt, theo thứ tự nhãn: {', '.join(labels)}.\n"
    else:
        others = "\n".join(f"- {item['text']}" for place, item in enumerate(current or []) if place != only)
        ask = (
            f"Viết lại ĐÚNG 1 bình luận tiếng Việt với nhãn: {labels[only]}.\n"
            f"Các bình luận còn lại của bài (đừng lặp ý):\n{others}\n"
        )
    rules = (
        "Ý nghĩa nhãn:\n"
        "- cong_dung: 2–3 lợi ích chính | cach_lam: cách chế biến/ăn đúng để giữ chất\n"
        "- luu_y: lượng ăn, thời điểm, bảo quản | nen_dung: ai hợp | han_che: ai nên hạn chế/hỏi bác sĩ\n"
        "- tac_hai: vì sao nên hạn chế | thay_the: lựa chọn thay thế | can_tranh: ai cần tránh nhất\n"
        "- an_it_hai: nếu vẫn ăn thì ăn sao cho đỡ hại\n"
        "Yêu cầu: mỗi bình luận 2–3 câu, giọng gần gũi; không hứa chữa bệnh; không mâu thuẫn caption;\n"
        "bình luận về đối tượng hạn chế phải khuyên hỏi bác sĩ khi có bệnh nền; không emoji, không hashtag, không link.\n"
        f'Chỉ trả về JSON: {{"pinned_comments":[{{"type":"...","text":"..."}}{", ..." if only is None else ""}]}}'
    )
    return head + ask + rules


def parse_output(raw: str, kind: str | None, only: int | None = None) -> list[dict]:
    """The comments of the AI's answer, in the order of the label set; raises ScriptOutputError for what a retry
    may fix: not JSON, a wrong count, a text out of bounds, a promise a Page may not make."""
    data = json_object(raw)
    items = data.get("pinned_comments")
    if not isinstance(items, list):
        raise ScriptOutputError("thiếu pinned_comments")
    want = 1 if only is not None else MAX_COMMENTS
    if len(items) != want:
        raise ScriptOutputError(f"cần đúng {want} bình luận, có {len(items)}")
    labels = type_set(kind)
    out = []
    for place, item in enumerate(items):
        text = item.get("text") if isinstance(item, dict) else None
        if not isinstance(text, str):
            raise ScriptOutputError(f"bình luận {place + 1} thiếu text")
        text = " ".join(unicodedata.normalize("NFC", text).split())
        if not MIN_TEXT <= len(text) <= MAX_TEXT:
            raise ScriptOutputError(f"bình luận {place + 1} dài {len(text)} ký tự")
        hits = sensitive_hits(text)
        if hits:
            raise ScriptOutputError(f"bình luận {place + 1} có từ nhạy cảm “{hits[0]}”")
        out.append({"type": labels[only if only is not None else place], "text": text})
    return out


def generate(
    prompt: str, kind: str | None, only: int | None, label: str, on_call: Callable[[], None], call
) -> list[dict]:
    """Asked again when the answer is unusable or promises a cure: three tries in all, then given up with the raw
    answer as the detail."""
    problem = None
    raw = ""
    for _try in range(AI_TRIES):
        raw = call(prompt, label)
        on_call()
        try:
            return parse_output(raw, kind, only)
        except ScriptOutputError as err:
            problem = err
    raise ClaudeError(
        f"AI trả bình luận không đúng ({problem}), đã thử {AI_TRIES} lần", f"Câu trả lời thô:\n{raw[:8000]}"
    )


def run_job(db: DbSession, job: Job, call, count_call) -> None:
    """A slot_comments job: the AI writes the script's comments, or one of them (`params.index`). A script a member
    edited by hand is left alone unless the job was made by their own click (`params.overwrite`)."""
    from .jobs import JobFailure

    slot = db.get(ArticlePlanSlot, job.plan_slot_id)
    if slot is None:
        raise JobFailure("Kịch bản đã bị xoá")
    params = job.params or {}
    only = params.get("index") if isinstance(params.get("index"), int) else None
    if slot.comments_edited and not params.get("overwrite"):
        return
    plan = db.get(ArticlePlan, slot.plan_id)
    page = db.get(Fanpage, plan.fanpage_id)
    current = comments_of(slot)
    if only is not None and (not 0 <= only < len(current) or len(current) != MAX_COMMENTS):
        only = None
    prompt = build_prompt(page.name, plan.audience, slot.hook, slot.kind, _caption(slot), only=only, current=current)
    try:
        written = generate(prompt, slot.kind, only, f"job {job.id}", count_call, call)
    except ClaudeError as err:
        raise JobFailure(err.message, err.detail) from None
    slot = db.get(ArticlePlanSlot, job.plan_slot_id, with_for_update=True, populate_existing=True)
    if slot is None:
        raise JobFailure("Kịch bản đã bị xoá")
    if only is not None:
        items = comments_of(slot)
        if len(items) != MAX_COMMENTS:
            raise JobFailure("Bình luận của kịch bản đã đổi, hãy tạo lại")
        items[only] = written[0]
        written = items
    checked = check(written, slot.pin_index, slot.kind)
    set_comments(slot, checked, "ai", edited=bool(only is not None and slot.comments_edited))
    db.commit()


def _caption(slot: ArticlePlanSlot) -> str:
    from .article_plans import caption_of

    return caption_of(slot)


# --- "Tạo bình luận ghim" ---


def queue(db: DbSession, slots: list[ArticlePlanSlot], user_id: int, overwrite: bool, index: int | None = None) -> int:
    """A slot_comments job for each script that has none queued; returns how many were queued. A script edited by hand
    is skipped unless `overwrite`."""
    queued = 0
    for slot in slots:
        if slot.comments_edited and not overwrite:
            continue
        if db.scalar(
            select(Job.id).where(
                Job.plan_slot_id == slot.id, Job.kind == JOB_KIND, Job.status.in_(("queued", "running"))
            )
        ):
            continue
        params: dict = {"overwrite": overwrite}
        if index is not None:
            params["index"] = index
        db.add(Job(kind=JOB_KIND, status="queued", created_by_id=user_id, plan_slot_id=slot.id, params=params))
        queued += 1
    db.flush()
    return queued


def scope_slots(db: DbSession, plan: ArticlePlan, scope: str, ids: list[int]) -> list[ArticlePlanSlot]:
    """The scripts a bulk run covers: the unused ones short of 5 comments, the chosen ones, or every script not yet
    posted."""
    slots = db.scalars(
        select(ArticlePlanSlot)
        .where(ArticlePlanSlot.plan_id == plan.id, ArticlePlanSlot.skipped.is_(False))
        .order_by(ArticlePlanSlot.day.nulls_last(), ArticlePlanSlot.slot, ArticlePlanSlot.id)
    ).all()
    if scope == "selected":
        return [slot for slot in slots if slot.id in ids]
    unposted = [slot for slot in slots if not _posted(db, slot)]
    if scope == "unposted":
        return unposted
    return [slot for slot in unposted if slot.article_id is None and len(comments_of(slot)) < MAX_COMMENTS]


def _posted(db: DbSession, slot: ArticlePlanSlot) -> bool:
    if slot.article_id is None:
        return False
    return (
        db.scalar(
            select(Publication.id).where(
                Publication.article_id == slot.article_id, Publication.status.in_(("scheduled", "published"))
            )
        )
        is not None
    )


def progress(db: DbSession, plan_id: int) -> int:
    """How many "Tạo bình luận ghim" jobs of the plan are still queued or running."""
    return (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .join(ArticlePlanSlot, ArticlePlanSlot.id == Job.plan_slot_id)
            .where(ArticlePlanSlot.plan_id == plan_id, Job.kind == JOB_KIND, Job.status.in_(("queued", "running")))
        )
        or 0
    )


def job_state(db: DbSession, slot_id: int) -> dict:
    """Whether a "Tạo bình luận ghim" job of the script is queued or running, and why the last one failed."""
    last = db.scalar(
        select(Job).where(Job.plan_slot_id == slot_id, Job.kind == JOB_KIND).order_by(Job.id.desc()).limit(1)
    )
    return {
        "comments_pending": last is not None and last.status in ("queued", "running"),
        "comments_error": last.error if last is not None and last.status == "failed" else None,
    }


def summary(rows: list[dict]) -> dict:
    """The plan's line "Bình luận: 72/87 kịch bản đủ 5/5" over the scripts on its grid."""
    return {
        "full": sum(1 for row in rows if row["comments_count"] >= MAX_COMMENTS),
        "total": len(rows),
    }


def slot_fields(slot: ArticlePlanSlot) -> dict:
    items = comments_of(slot)
    return {
        "pinned_comments": [{"type": item.get("type"), "text": item["text"]} for item in items],
        "pin_index": pin_of(slot),
        "comments_count": len(items),
        "comments_source": slot.comments_source,
        "comments_edited": slot.comments_edited,
        "type_set": list(type_set(slot.kind)),
    }


# --- Writing them under a post ---


def _random_seconds(span: tuple[int, int]) -> timedelta:
    return timedelta(seconds=random.uniform(*span))


def _sequence(rows: list) -> list:
    """The order they are written: the one to pin first, then the others as the script has them."""
    return sorted(rows, key=lambda row: (not row.is_pinned, row.order))


def rows_of(db: DbSession, publication_id: int) -> list:
    return list(
        db.scalars(
            select(PostComment)
            .where(PostComment.publication_id == publication_id)
            .order_by(PostComment.order)
            .execution_options(populate_existing=True)
        )
    )


def _live(post: Publication) -> bool:
    return post.remote_id is not None and (
        post.status == "published" or (post.status == "scheduled" and post.scheduled_at <= now())
    )


def start(db: DbSession, post: Publication) -> bool:
    """Makes the post's `post_comments` from its script's comments, once: only when the article asks for them, the
    script has some, and the post went live recently. Returns whether any were made. The caller commits."""
    if post.article_id is None or rows_of(db, post.id):
        return False
    article = db.get(Article, post.article_id)
    slot = db.scalar(select(ArticlePlanSlot).where(ArticlePlanSlot.article_id == post.article_id))
    if article is None or slot is None or not article.post_comments_enabled:
        return False
    items = comments_of(slot)[:MAX_COMMENTS]
    if not items:
        return False
    if live_at(post) < now() - START_WITHIN:
        return False
    pin = pin_of(slot)
    rows = [
        PostComment(
            publication_id=post.id,
            script_id=slot.id,
            order=place,
            text=item["text"],
            type=(item.get("type") or None) and item["type"][:16],
            is_pinned=place == pin,
        )
        for place, item in enumerate(items)
    ]
    rows[pin].due_at = now() + _random_seconds(FIRST_DELAY)
    # The others wait for the one before them: their time is set when it has been written.
    for row in rows:
        if row is not rows[pin]:
            row.due_at = None
    db.add_all(rows)
    db.flush()
    return True


def _gone(err: FacebookError) -> bool:
    return err.status in (400, 404) and ((err.code == 100 and err.subcode == 33) or err.code == 803)


def attempt(db: DbSession, post: Publication, row) -> None:
    """One try at writing a comment: stamped before Facebook is asked, so an answer lost on the way never writes it
    twice (the next try looks for a comment of the Page with the same text first). Commits."""
    if row.fb_comment_id:
        # Never written twice: a comment with an id only moves on.
        row.status = "need_manual_pin" if row.is_pinned else "posted"
        _advance(db, post, row)
        return
    before = row.attempts
    row.attempts += 1
    db.commit()
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        found = facebook.page_comment(page, post.remote_id, row.text) if before else None
        row.fb_comment_id = found or facebook.post_comment(page, post.remote_id, row.text)
    except FacebookError as err:
        _failed(db, post, row, err)
        return
    row.status = "need_manual_pin" if row.is_pinned else "posted"
    row.error, row.posted_at = None, now()
    _advance(db, post, row)
    log.info("Wrote comment %s of post %s as %s", row.order + 1, post.id, row.fb_comment_id)


def _advance(db: DbSession, post: Publication, row) -> None:
    """The next comment in line is due a little later than this one."""
    following = next((other for other in _sequence(rows_of(db, post.id)) if other.status == "pending"), None)
    if following is not None and following.id != row.id:
        following.due_at = now() + _random_seconds(GAP)
    db.commit()


def _failed(db: DbSession, post: Publication, row, err: FacebookError) -> None:
    log.warning("Could not write comment %s of post %s: %s %s", row.order + 1, post.id, err.message, err.detail)
    row.error = err.message
    if _gone(err):
        # The post is gone: what is left is not written.
        row.status = "skipped"
        for other in rows_of(db, post.id):
            if other.status == "pending":
                other.status, other.error = "skipped", "Bài đã bị xoá hoặc không tìm thấy"
    elif facebook.is_passing(err) and row.attempts <= len(RETRY_MINUTES):
        row.due_at = now() + timedelta(minutes=RETRY_MINUTES[row.attempts - 1])
    elif facebook.is_passing(err):
        row.status = "failed"
        _advance(db, post, row)
        return
    else:
        # A permission or token: nothing changes by trying again, so the rest stops here too.
        row.status = "failed"
        for other in rows_of(db, post.id):
            if other.status == "pending":
                other.status, other.error = "failed", err.message
    db.commit()


def due_posts(db: DbSession, limit: int = BATCH) -> list[int]:
    """Live posts of articles that have a comment due now, or whose comments are not made yet and may be (a script with
    comments, a post live for less than START_WITHIN). Ids, oldest first."""
    at = now()
    waiting = select(PostComment.publication_id).where(PostComment.status == "pending", PostComment.due_at <= at)
    started = select(PostComment.publication_id)
    has_comments = exists().where(
        ArticlePlanSlot.article_id == Publication.article_id,
        func.jsonb_array_length(ArticlePlanSlot.pinned_comments) > 0,
    )
    live_since = func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)
    posts = db.scalars(
        select(Publication)
        .join(Article, Article.id == Publication.article_id)
        .where(
            Publication.platform == "facebook",
            Publication.remote_id.is_not(None),
            Publication.status.in_(("published", "scheduled")),
            Article.post_comments_enabled.is_(True),
            or_(
                Publication.id.in_(waiting),
                and_(Publication.id.not_in(started), has_comments, live_since >= at - START_WITHIN),
            ),
        )
        .order_by(Publication.id)
        .limit(limit * 4)
    ).all()
    return [post.id for post in posts if _live(post)][:limit]


def write_post(db: DbSession, post_id: int) -> None:
    post = db.get(Publication, post_id, with_for_update=True, populate_existing=True)
    if post is None or not _live(post):
        return
    if start(db, post):
        db.commit()
    rows = _sequence(rows_of(db, post.id))
    row = next((item for item in rows if item.status == "pending"), None)
    if row is None or (row.due_at is not None and row.due_at > now()):
        return
    attempt(db, post, row)


def run_due(factory: sessionmaker) -> None:
    """One round of the worker. Nothing here may stop the queue: a failure is logged and the next round goes on."""
    try:
        with factory() as db:
            ids = due_posts(db)
    except Exception:
        log.exception("Could not look for pinned comments to write")
        return
    for post_id in ids:
        try:
            with factory() as db:
                write_post(db, post_id)
        except Exception:
            log.exception("Could not write pinned comments of post %s", post_id)


# --- Members' actions on a posted article ---

ROW_LABELS = {
    "pending": "Chờ đăng",
    "posted": "Đã đăng",
    "pinned": "Đã ghim",
    "need_manual_pin": "Chờ ghim tay",
    "failed": "Lỗi",
    "skipped": "Bỏ qua",
}


def retry_failed(db: DbSession, post: Publication) -> int:
    """ "Đăng lại bình luận lỗi": each failed comment without a Facebook id is tried again, the first now and the
    others after it; one already written is never written again. Returns how many."""
    count = 0
    first = True
    for row in _sequence(rows_of(db, post.id)):
        if row.status != "failed":
            continue
        if row.fb_comment_id:
            row.status = "need_manual_pin" if row.is_pinned else "posted"
            continue
        row.status, row.error, row.attempts = "pending", None, 0
        row.due_at = now() if first else None
        first = False
        count += 1
    db.flush()
    return count


def mark_pinned(db: DbSession, post: Publication) -> bool:
    """ "Đã ghim": the member pinned the comment on Facebook."""
    row = next((item for item in rows_of(db, post.id) if item.is_pinned and item.status == "need_manual_pin"), None)
    if row is None:
        return False
    row.status = "pinned"
    db.flush()
    return True


def post_payload(db: DbSession, post: Publication) -> dict | None:
    rows = rows_of(db, post.id)
    if not rows:
        return None
    waiting = next((row for row in rows if row.status == "need_manual_pin"), None)
    return {
        "items": [
            {
                "id": row.id,
                "order": row.order,
                "type": row.type,
                "type_label": TYPE_LABELS.get(row.type or ""),
                "text": row.text,
                "is_pinned": row.is_pinned,
                "status": row.status,
                "status_label": ROW_LABELS[row.status],
                "error": row.error,
                "attempts": row.attempts,
                "posted_at": row.posted_at.isoformat() if row.posted_at else None,
            }
            for row in rows
        ],
        "written": sum(1 for row in rows if row.fb_comment_id),
        "total": len(rows),
        "failed": sum(1 for row in rows if row.status == "failed"),
        "need_manual_pin": waiting is not None,
        "url": facebook.post_url(post.remote_id) if post.remote_id else None,
    }
