"""Affiliate comment sets ("Bộ bình luận", docs/decisions/2026-11-19-aff-comment-sets.md): a Page keeps ready-made
comments of up to MAX_ITEMS approved products each, and the worker writes one to three of them under each reel after
the food comments (post_comments.py), so no link is pasted by hand.

- **Which sets** (`plan_sets`): a video's own choice when it made one, else `choose` over the Page's enabled sets with
  at least MIN_VALID usable products: the set whose tags (its own and its products') appear most in the video's title,
  scenes and topic first (`match_then_rotate`), the rest the sets free to use taking turns by video (`_in_turn`, so
  videos not posted yet show different sets); a set used on the Page within `no_repeat_days` only when nothing else
  is left. The choice is the same every time it is asked until the first set
  comment is written, then kept on the post (`publications.aff_set_ids`).
- **What a comment says** (`render`): the opening line, one line per product (`line_format`, numbered from 1), the
  closing line. Products no longer usable are left out and the rest renumbered; a product already in an earlier set
  of the same post is left out too; at most `products_per_comment`, and never past Facebook's 8000 characters.
- **Links** are the ones the pinned comment uses (affiliate.link_for): the Page's own Shopee account makes one per
  video and Page (its sub_ids name both), or the link saved on the product.
"""

import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from . import affiliate, pinned
from .errors import ApiError
from .models import AffCommentSet, AffCommentSetItem, AffiliateProduct, Fanpage, Publication, Video
from .sessions import now

MAX_ITEMS = 10
MIN_VALID = 3  # a set with fewer usable products is left out of the choice
MAX_SETS_PER_POST = 3
MAX_TAGS = 20
MAX_TAG_LENGTH = 40
MAX_SHORT_NAME_LENGTH = 60
MAX_CATEGORY_LENGTH = 60
STRATEGIES = {
    "match_then_rotate": "Khớp chủ đề rồi xoay vòng",
    "rotate": "Xoay vòng",
    "random": "Ngẫu nhiên theo ưu tiên",
}
DEFAULTS: dict = {
    "enabled": True,
    "sets_per_post": 2,
    "products_per_comment": 10,
    "strategy": "match_then_rotate",
    "no_repeat_days": 3,
    # Seconds: after the last food comment before the first set comment, and between two set comments.
    "first_delay": [300, 600],
    "delay": [180, 420],
    "line_format": "{stt}. {short_name} 👉 {link}",
}
MAX_LINE_FORMAT = 200
# Opening lines for "Tạo tự động từ kho", a different one per set so the Page's comments do not all read the same.
INTROS = [
    "👉 Mấy món nhà mình hay dùng để ăn healthy:",
    "🛒 Đồ bếp, đồ ăn nhà mình tin dùng, ai cần thì xem nhé:",
    "💚 Gợi ý vài món ngon lành cho bữa ăn nhà mình:",
    "📌 Danh sách đồ ăn sạch mình hay mua:",
    "🌿 Ai hỏi mua ở đâu thì đây nhé:",
    "✨ Mấy món này nhà mình dùng hoài:",
    "🥗 Đồ ăn lành mạnh cho cả nhà, lưu lại nhé:",
    "🍵 Vài món mình hay đặt về dùng dần:",
    "👇 Link mấy món mọi người hay hỏi:",
    "🧺 Giỏ đồ ăn healthy nhà mình:",
    "🌾 Ngũ cốc, hạt, đồ khô nhà mình hay dùng:",
    "🍳 Mấy món tiện cho căn bếp nhỏ:",
]
OUTRO = "Bấm link xem giá mới nhất nhé, giá có thể thay đổi."
SPLITS = {"by_category": "Theo nhóm", "random": "Ngẫu nhiên", "mixed": "Trộn mỗi bộ đủ nhóm"}
NO_CATEGORY = "Khác"


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


# Settings


def settings_of(page: Fanpage | None) -> dict:
    """The Page's settings, DEFAULTS filling what was never saved."""
    saved = (page.aff_settings if page is not None else None) or {}
    return {name: saved.get(name, default) for name, default in DEFAULTS.items()}


def _whole(value, low: int, high: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise invalid(f"{label} phải từ {low} đến {high}")
    return value


def _span(value, low: int, high: int, label: str) -> list[int]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise invalid(f"{label} cần 2 số: ít nhất và nhiều nhất")
    first, last = (_whole(part, low, high, label) for part in value)
    if first > last:
        raise invalid(f"{label}: số đầu không được lớn hơn số sau")
    return [first, last]


def clean_settings(raw: dict) -> dict:
    """The settings a member saved, checked; what is not given keeps its default."""
    merged = {name: raw.get(name, default) for name, default in DEFAULTS.items()}
    line_format = unicodedata.normalize("NFC", str(merged["line_format"] or "")).strip()
    if "{link}" not in line_format:
        raise invalid("Mẫu dòng phải có {link}")
    if len(line_format) > MAX_LINE_FORMAT:
        raise invalid(f"Mẫu dòng dài quá {MAX_LINE_FORMAT} ký tự")
    if merged["strategy"] not in STRATEGIES:
        raise invalid("Cách chọn bộ không hợp lệ")
    return {
        "enabled": bool(merged["enabled"]),
        "sets_per_post": _whole(merged["sets_per_post"], 1, MAX_SETS_PER_POST, "Số bộ mỗi bài"),
        "products_per_comment": _whole(merged["products_per_comment"], 1, MAX_ITEMS, "Số sản phẩm mỗi bình luận"),
        "strategy": merged["strategy"],
        "no_repeat_days": _whole(merged["no_repeat_days"], 0, 30, "Số ngày không lặp lại"),
        "first_delay": _span(merged["first_delay"], 0, 3600, "Chờ trước bình luận aff đầu (giây)"),
        "delay": _span(merged["delay"], 30, 3600, "Nghỉ giữa các bình luận aff (giây)"),
        "line_format": line_format,
    }


def clean_tags(values: list[str]) -> list[str]:
    """Tags as matched: lower case, one Unicode form, single spaces, each once, in the order given."""
    tags: list[str] = []
    for value in values:
        tag = normalize(value)
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise invalid(f"Tag “{tag[:20]}…” dài quá {MAX_TAG_LENGTH} ký tự")
        if tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise invalid(f"Tối đa {MAX_TAGS} tag")
    return tags


def _label_line(value: str | None, limit: int, label: str) -> str:
    value = unicodedata.normalize("NFC", value or "").strip()
    if "\n" in value or "\r" in value:
        raise invalid(f"{label} chỉ một dòng")
    if len(value) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return value


def clean_labels(short_name: str | None, category: str | None, tags: list[str]) -> tuple[str | None, str | None, list]:
    """A product's short name, group and tags as saved ("Bộ bình luận" tab or an imported file); empty is None."""
    short = _label_line(short_name, MAX_SHORT_NAME_LENGTH, "Tên ngắn")
    group = _label_line(category, MAX_CATEGORY_LENGTH, "Nhóm")
    return short or None, group or None, clean_tags(tags)


def split_tags(cell: str) -> list[str]:
    """The tags of a file's cell: separated by commas, semicolons or "|"."""
    return [part for part in re.split(r"[,;|]", cell or "") if part.strip()]


# Choosing the sets


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").casefold().split())


def matches(tag: str, text: str) -> bool:
    """The tag appears in the text as whole words ("cá" is not found in "các")."""
    return bool(tag) and re.search(rf"(?<!\w){re.escape(tag)}(?!\w)", text) is not None


@dataclass
class Candidate:
    id: int
    priority: int
    last_used_at: datetime | None
    tags: list[str]
    valid: int
    enabled: bool = True


def score(candidate: Candidate, text: str) -> int:
    """How well a set fits the video: 10 for every tag found in its text, plus the set's priority; 0 when none."""
    found = sum(1 for tag in candidate.tags if matches(tag, text))
    return found * 10 + candidate.priority if found else 0


def _rotation(candidates: list[Candidate]) -> list[Candidate]:
    # The longest unused first; higher priority and the older set break a tie.
    return sorted(
        candidates,
        key=lambda one: (one.last_used_at is not None, one.last_used_at or datetime.min, -one.priority, one.id),
    )


def _in_turn(candidates: list[Candidate], seed: int, step: int) -> list[Candidate]:
    """Sets equally free to use, in a cycle (higher priority, then the older set) that the video's id starts at its
    own place, `step` further for each next video: videos made one after another show and get different sets, not
    the same ones until one goes up."""
    cycle = sorted(candidates, key=lambda one: (-one.priority, one.id))
    if not cycle:
        return []
    start = (seed * step) % len(cycle)
    return cycle[start:] + cycle[:start]


def choose(candidates: list[Candidate], text: str, settings: dict, at: datetime, seed: int) -> list[int]:
    """The ids of the sets to write under a video whose matching text is `text` (normalized), best first. The same
    inputs always give the same answer: "random" draws with the video's own seed."""
    wanted = settings["sets_per_post"]
    pool = [one for one in candidates if one.enabled and one.valid >= MIN_VALID]
    window = timedelta(days=settings["no_repeat_days"])
    fresh = [one for one in pool if one.last_used_at is None or at - one.last_used_at >= window]
    stale = [one for one in pool if one not in fresh]
    picks: list[Candidate] = []
    if settings["strategy"] == "random":
        draw = random.Random(seed)
        for group in (fresh, stale):
            left = list(group)
            while left and len(picks) < wanted:
                one = draw.choices(left, weights=[max(1, item.priority) for item in left])[0]
                picks.append(one)
                left.remove(one)
        return [one.id for one in picks]
    if settings["strategy"] == "match_then_rotate":
        scored = [(score(one, text), one) for one in (fresh or stale)]
        top = max((points for points, _ in scored), default=0)
        if top > 0:
            # Sets matching equally well take turns too.
            picks.extend(_in_turn([one for points, one in scored if points == top], seed, 1)[:1])
    # Fresh sets (not used within no_repeat_days) are equally free: they take turns by video. Recent ones come back
    # only when too few are fresh, the longest unused first.
    for one in _in_turn(fresh, seed, wanted) + _rotation(stale):
        if len(picks) >= wanted:
            break
        if one not in picks:
            picks.append(one)
    return [one.id for one in picks]


def counts(product: AffiliateProduct) -> bool:
    """A product a set comment may carry: an approved Shopee product still meeting the rules, with a link to give."""
    return product.platform == "shopee" and bool(product.url or product.page_url) and affiliate.usable(product)


def label(product: AffiliateProduct) -> str:
    return product.short_name or product.name


def page_sets(db: DbSession, fanpage_id: int) -> list[AffCommentSet]:
    return list(
        db.scalars(select(AffCommentSet).where(AffCommentSet.fanpage_id == fanpage_id).order_by(AffCommentSet.id))
    )


def candidate(one: AffCommentSet) -> Candidate:
    valid = [item.product for item in one.items if counts(item.product)]
    tags = list(one.tags or [])
    for product in valid:
        tags.extend(tag for tag in (product.tags or []) if tag not in tags)
    return Candidate(one.id, one.priority, one.last_used_at, tags, len(valid), one.enabled)


def video_text(db: DbSession, video: Video) -> str:
    """What a set's tags are looked for in: the video's title and scene names (its pinned comment) and its topic."""
    return normalize(f"{pinned.text_of(db, video)}\n{video.topic or ''}")


def wants_sets(video: Video | None) -> bool:
    return (
        video is not None and video.platform == "facebook" and not video.aff_comments_off and not video.manual_comment
    )


def plan_sets(db: DbSession, video: Video, page: Fanpage, at: datetime | None = None) -> list[AffCommentSet]:
    """The sets the Page would write under the video now: none when off for the Page or the video, the video's own
    choice when one of them is the Page's, else the app's (`choose`)."""
    if not wants_sets(video) or not settings_of(page)["enabled"]:
        return []
    sets = page_sets(db, page.id)
    if not sets:
        return []
    by_id = {one.id: one for one in sets}
    own = [by_id[set_id] for set_id in (video.aff_set_ids or []) if set_id in by_id]
    if own:
        return own
    chosen = choose([candidate(one) for one in sets], video_text(db, video), settings_of(page), at or now(), video.id)
    return [by_id[set_id] for set_id in chosen]


# What a comment says


def render(intro: str, outro: str, rows: list[tuple[str, str]], line_format: str) -> str:
    """The comment: the opening line, one line per (name, link) numbered from 1, the closing line; the last products
    are dropped while it is longer than Facebook takes."""
    rows = list(rows)
    while True:
        lines = [
            line_format.replace("{stt}", str(place)).replace("{short_name}", name).replace("{link}", link)
            for place, (name, link) in enumerate(rows, start=1)
        ]
        text = "\n".join(part for part in [intro.strip(), *lines, outro.strip()] if part)
        if len(text) <= affiliate.MAX_COMMENT_LENGTH or not rows:
            return text
        rows.pop()


def _rows(products: list[AffiliateProduct], seen: set[int], limit: int, link_of) -> list[tuple[str, str]]:
    rows = []
    for product in products:
        if len(rows) >= limit:
            break
        if product.id in seen or not counts(product):
            continue
        link = link_of(product)
        if not link:
            continue
        seen.add(product.id)
        rows.append((label(product), link))
    return rows


def comments_for(db: DbSession, post: Publication) -> list[tuple[int, str]]:
    """The set comments to write under a Facebook post of a video, as (set id, text): those of the sets kept on the
    post once one was written, else of the sets planned now. None when the Page or the video has them off. Makes the
    Page's Shopee links as the pinned comment does; raises ShopeeError when Shopee cannot."""
    video = db.get(Video, post.video_id) if post.video_id else None
    page = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
    if page is None or not wants_sets(video):
        return []
    settings = settings_of(page)
    if not settings["enabled"]:
        return []
    if post.aff_set_ids is not None:
        sets = [one for one in (db.get(AffCommentSet, set_id) for set_id in post.aff_set_ids) if one is not None]
    else:
        sets = plan_sets(db, video, page)
    account = affiliate.page_account(db, page)
    seen: set[int] = set()
    comments = []
    for one in sets:
        products = [item.product for item in one.items]
        rows = _rows(
            products,
            seen,
            settings["products_per_comment"],
            lambda product: affiliate.link_for(db, product, post, account),
        )
        if rows:
            comments.append((one.id, render(one.intro_text, one.outro_text, rows, settings["line_format"])))
    return comments


def preview_rows(one: AffCommentSet, seen: set[int], settings: dict) -> list[tuple[str, str]]:
    """A set's lines before a post exists: the link saved on the product, or its Shopee page (the Page's own account
    makes the real one when the comment is written)."""
    products = [item.product for item in one.items]
    return _rows(products, seen, settings["products_per_comment"], lambda product: product.url or product.page_url)


def preview(db: DbSession, video: Video, page: Fanpage) -> list[dict]:
    settings = settings_of(page)
    seen: set[int] = set()
    out = []
    for one in plan_sets(db, video, page):
        rows = preview_rows(one, seen, settings)
        out.append(
            {
                "set_id": one.id,
                "set_name": one.name,
                "products": len(rows),
                "text": render(one.intro_text, one.outro_text, rows, settings["line_format"]),
            }
        )
    return out


def summaries(db: DbSession, pages: list[Fanpage]) -> dict[int, dict]:
    """Each Page's line on "Quản lý kênh": its sets switched on or off, how many it has, how many the worker may
    choose now (on, with at least MIN_VALID usable products), and how many go under a reel."""
    out = {page.id: {"enabled": settings_of(page)["enabled"], "sets": 0, "usable": 0, "per_post": 0} for page in pages}
    query = (
        select(AffCommentSet)
        .where(AffCommentSet.fanpage_id.in_(list(out) or [0]))
        .options(selectinload(AffCommentSet.items).selectinload(AffCommentSetItem.product))
    )
    for one in db.scalars(query):
        row = out[one.fanpage_id]
        row["sets"] += 1
        if one.enabled and candidate(one).valid >= MIN_VALID:
            row["usable"] += 1
    for page in pages:
        out[page.id]["per_post"] = settings_of(page)["sets_per_post"]
    return out


def mark_used(db: DbSession, set_id: int) -> None:
    one = db.get(AffCommentSet, set_id)
    if one is not None:
        one.last_used_at = now()
        one.use_count += 1


def ask_set_refresh(db: DbSession, set_ids: list[int]) -> int:
    """A set changed (its lines, its products' links or names): ask the worker to edit the set comments already
    written under live posts that used it, as affiliate.ask_comment_refresh does for the pinned comment. Does not
    commit."""
    if not set_ids:
        return 0
    at, asked = now(), 0
    contains = [Publication.aff_set_ids.contains([set_id]) for set_id in set_ids]
    posts = db.scalars(
        select(Publication).where(
            Publication.platform == "facebook",
            Publication.aff_set_ids.is_not(None),
            Publication.status.in_(("published", "scheduled")),
            or_(*contains),
        )
    )
    for post in posts:
        live = post.status == "published" or (post.scheduled_at is not None and post.scheduled_at <= at)
        resting = post.comment_requested_at is not None and post.comment_requested_at > at
        if live and post.aff_comment_ids and not resting:
            post.comment_requested_at = at
            asked += 1
    return asked


def sets_of_products(db: DbSession, product_ids: list[int]) -> list[int]:
    if not product_ids:
        return []
    return list(
        db.scalars(select(AffCommentSetItem.set_id).where(AffCommentSetItem.product_id.in_(product_ids)).distinct())
    )


# "Tạo tự động từ kho"


def split(products: list[AffiliateProduct], how: str, per_set: int, seed: int = 0) -> list[list[AffiliateProduct]]:
    """The products cut into sets of at most `per_set`: each group on its own (by_category, a group's last set may be
    short), all shuffled (random), or each set taking from every group in turn (mixed)."""
    if how not in SPLITS:
        raise invalid("Cách chia không hợp lệ")
    if how == "random":
        shuffled = list(products)
        random.Random(seed).shuffle(shuffled)
        return [shuffled[start : start + per_set] for start in range(0, len(shuffled), per_set)]
    groups: dict[str, list[AffiliateProduct]] = {}
    for product in products:
        groups.setdefault(product.category or NO_CATEGORY, []).append(product)
    names = sorted(groups, key=lambda name: (name == NO_CATEGORY, name))
    if how == "by_category":
        return [
            groups[name][start : start + per_set] for name in names for start in range(0, len(groups[name]), per_set)
        ]
    dealt: list[AffiliateProduct] = []
    queues = [list(groups[name]) for name in names]
    while any(queues):
        for queue in queues:
            if queue:
                dealt.append(queue.pop(0))
    return [dealt[start : start + per_set] for start in range(0, len(dealt), per_set)]


def set_name(number: int, products: list[AffiliateProduct], how: str) -> str:
    categories = sorted({product.category or NO_CATEGORY for product in products})
    topic = categories[0] if how == "by_category" and categories else "Tổng hợp"
    return f"Bộ {number:02d} – {topic}"
