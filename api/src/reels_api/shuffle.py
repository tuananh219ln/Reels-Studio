"""'Nhân bản xáo cảnh': copies of a video, each with its content scenes in another order and their list numbers
("1.", "2)"…) at the start of the on-screen text and the voice text written again for their new place. The title
scene stays first; "Giữ cố định cảnh cuối" keeps the last scene (a closing/CTA scene) where it is, and a pinned scene
("Ghim cảnh") keeps its place too. A copy asks for a
new title until its title scene says something else (docs/decisions/2026-11-17-shuffle-copies.md)."""

import math
import random
import re
from itertools import permutations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from .duplicate import copy_video, with_suffix
from .errors import ApiError
from .models import Scene, Video
from .script_rules import plain_title
from .storage import DirectoryStorage
from .videos import split_scenes, title_of, video_name

MAX_COPIES = 20
# With this many scenes to move, every order is listed and drawn from; above it, orders are drawn at random.
LIST_ALL_UP_TO = 6
# "Khác nhiều": from 4 scenes on, an order where at least half the scenes moved is preferred.
FAR_FROM = 4
FAR_SHARE = 0.5
# A list number at the very start: "1. ", "2) ", "3: ", "4 - ", "#5. ", "Số 6: ", "Cách 7. ", "Món 8) ", "Bước 9.".
# Its mark must not run into a digit, so "1.5 kg" and "3-4 lần" are not list numbers; "50 tuổi" has no mark at all.
LIST_PREFIX = re.compile(r"^(\s*)(#|(?:Số|Cách|Món|Bước)\s+)?(\d{1,2})(\s*[.):\-](?!\d)\s*)", re.IGNORECASE)


def renumber(text: str, number: int) -> str:
    """`text` with the list number at its start made `number`, its word, mark and spaces kept; unchanged without one."""
    match = LIST_PREFIX.match(text)
    if match is None:
        return text
    lead, word, _, mark = match.groups()
    return f"{lead}{word or ''}{number}{mark}{text[match.end() :]}"


def list_number(text: str) -> int | None:
    match = LIST_PREFIX.match(text)
    return int(match.group(3)) if match else None


def numbered(scenes: list[Scene]) -> tuple[bool, list[str]]:
    """Whether the scenes are a numbered list worth renumbering: at least half of them open with a list number. The
    warnings say what looks off (numbers not 1, 2, 3… in order)."""
    numbers = [list_number(scene.text) for scene in scenes]
    found = [number for number in numbers if number is not None]
    if not scenes or len(found) < len(scenes) * 0.5:
        return False, []
    warnings = []
    if found != list(range(1, len(found) + 1)) or len(found) < len(scenes):
        warnings.append("Số thứ tự ở chữ các cảnh không liền nhau 1, 2, 3…; đã đánh lại theo vị trí mới")
    return True, warnings


def distinct_orders(count: int) -> int:
    """How many orders other than the original `count` free scenes can take."""
    return math.factorial(count) - 1 if count >= 2 else 0


def _moved_share(original: tuple, order: tuple) -> float:
    return sum(a != b for a, b in zip(original, order, strict=True)) / len(original)


def generate_orders(
    ids: list[int],
    locked: set[int],
    count: int,
    taken: set[tuple[int, ...]] = frozenset(),
    rng: random.Random | None = None,
) -> list[list[int]]:
    """Up to `count` orders of `ids`, each other than the original, than `taken` and than one another; the positions in
    `locked` keep their id. Orders where at least half the scenes moved come first when there are enough scenes."""
    rng = rng or random.Random()
    original = tuple(ids)
    free = [index for index in range(len(ids)) if index not in locked]
    seen = {original, *taken}

    def place(moved) -> tuple[int, ...]:
        order = list(ids)
        for index, scene_id in zip(free, moved, strict=True):
            order[index] = scene_id
        return tuple(order)

    def far(order: tuple) -> bool:
        return len(free) < FAR_FROM or _moved_share(original, order) >= FAR_SHARE

    if len(free) <= LIST_ALL_UP_TO:
        every = [order for order in map(place, permutations([ids[i] for i in free])) if order not in seen]
        rng.shuffle(every)
        every.sort(key=lambda order: not far(order))  # stable: the far ones first, each group still shuffled
        return [list(order) for order in every[:count]]
    out: list[tuple[int, ...]] = []
    tries = 0
    while len(out) < count and tries < count * 200:
        tries += 1
        moved = [ids[i] for i in free]
        rng.shuffle(moved)
        order = place(moved)
        if order in seen or (tries < count * 20 and not far(order)):
            continue
        seen.add(order)
        out.append(order)
    return [list(order) for order in out]


def _key(scene: Scene) -> int:
    """A scene as the first video of its copies knows it: a copy's scene by the scene it was copied from."""
    return scene.source_scene_id or scene.id


def _signature(keys) -> str:
    return ",".join(str(key) for key in keys)


def _root_id(video: Video) -> int:
    return video.shuffled_from_id or video.id


def _taken(db: DbSession, root_id: int, by_key: dict[int, int]) -> set[tuple[int, ...]]:
    """The orders the first video `root_id` and its copies already have, written with this video's scene ids (by_key:
    key → id); an order with a scene this video no longer has cannot come up again anyway."""
    root = db.scalars(
        select(Scene).where(Scene.video_id == root_id, Scene.is_title.is_(False)).order_by(Scene.position, Scene.id)
    ).all()
    signatures = [_signature(_key(scene) for scene in root)]
    signatures += db.scalars(
        select(Video.scene_order).where(Video.shuffled_from_id == root_id, Video.scene_order.is_not(None))
    ).all()
    taken = set()
    for signature in signatures:
        keys = [int(part) for part in signature.split(",") if part.isdigit()]
        if keys and all(key in by_key for key in keys):
            taken.add(tuple(by_key[key] for key in keys))
    return taken


def _locked(scenes: list[Scene], lock_last: bool, pinned=()) -> set[int]:
    """The places that keep their scene: the last one with `lock_last`, and those of the pinned scenes (by id)."""
    pinned = set(pinned)
    places = {index for index, scene in enumerate(scenes) if scene.id in pinned}
    return places | ({len(scenes) - 1} if lock_last and scenes else set())


def preview(db: DbSession, source: Video, count: int, lock_last: bool, pinned=()) -> dict:
    """The orders "Tạo N bản" would make, for the dialog to show; it makes them as shown. A pinned id that is not one
    of the source's content scenes is left out."""
    _, scenes = split_scenes(db, source)
    locked = _locked(scenes, lock_last, pinned)
    free = len(scenes) - len(locked)
    ids = [scene.id for scene in scenes]
    taken = _taken(db, _root_id(source), {_key(scene): scene.id for scene in scenes})
    orders = generate_orders(ids, locked, min(count, MAX_COPIES), taken)
    # The orders still free to take: those taken that keep the locked scene, other than this video's own.
    still_taken = [order for order in taken if order != tuple(ids) and all(order[i] == ids[i] for i in locked)]
    renumbering, warnings = numbered(scenes)
    if 0 < len(orders) < count:
        warnings.append(f"Chỉ tạo được {len(orders)} bản có thứ tự khác nhau")
    return {
        "free_scenes": free,
        "max_distinct": min(MAX_COPIES, max(0, distinct_orders(free) - len(still_taken))),
        "orders": orders,
        "pinned": [scenes[index].id for index in sorted(locked)],
        "scenes": [
            {"id": scene.id, "number": index, "name": _short(scene.text)} for index, scene in enumerate(scenes, 1)
        ],
        "numbered": renumbering,
        "warnings": warnings,
    }


def _short(text: str) -> str:
    first = text.replace("*", "").strip().splitlines()[0] if text.strip() else ""
    first = LIST_PREFIX.sub("", first).strip()
    return first if len(first) <= 40 else first[:39] + "…"


def used_titles(db: DbSession, source: Video) -> list[str]:
    """The titles the first video and its copies show now, for an assistant writing new ones not to repeat them."""
    root = _root_id(source)
    rows = db.scalars(
        select(Scene.text)
        .join(Video, Video.id == Scene.video_id)
        .where(Scene.is_title.is_(True), or_(Video.id == root, Video.shuffled_from_id == root))
        .order_by(Video.id)
    )
    return list(dict.fromkeys(plain_title(text) for text in rows if text.strip()))


def check_orders(db: DbSession, source: Video, orders: list[list[int]], lock_last: bool, pinned=()) -> list[Scene]:
    """Refuses orders that are not the source's content scenes in another order, that move the locked last scene or a
    pinned one, or that repeat; returns the source's content scenes."""
    _, scenes = split_scenes(db, source)
    ids = [scene.id for scene in scenes]
    if not set(pinned) <= set(ids):
        raise ApiError(409, "scenes_changed", "Cảnh đã ghim không còn trong video gốc, hãy xáo lại bản xem trước")
    kept = {index for index, scene_id in enumerate(ids) if scene_id in set(pinned)}
    if not orders:
        raise ApiError(422, "invalid_value", "Chưa có thứ tự cảnh nào để tạo")
    if len(orders) > MAX_COPIES:
        raise ApiError(422, "invalid_value", f"Tối đa {MAX_COPIES} bản mỗi lần")
    seen = {tuple(ids)}
    for order in orders:
        if sorted(order) != sorted(ids):
            raise ApiError(409, "scenes_changed", "Cảnh của video gốc vừa thay đổi, hãy xáo lại bản xem trước")
        if lock_last and order[-1] != ids[-1]:
            raise ApiError(422, "invalid_value", "Cảnh cuối phải đứng yên")
        if any(order[index] != ids[index] for index in kept):
            raise ApiError(422, "invalid_value", "Cảnh đã ghim phải đứng yên")
        if tuple(order) in seen:
            raise ApiError(422, "invalid_value", "Các bản phải có thứ tự cảnh khác nhau và khác video gốc")
        seen.add(tuple(order))
    return scenes


def _apply(scenes_in_order: list[Scene], renumbering: bool) -> None:
    """Gives the content scenes their places 1…N, and their list numbers too when the video is a numbered list. A
    new voice text makes its narration again at the next voice job or render (its signature no longer matches)."""
    for position, scene in enumerate(scenes_in_order, start=1):
        scene.position = position
        if renumbering:
            scene.text = renumber(scene.text, position)
            scene.voice_text = renumber(scene.voice_text, position)


def make_copies(
    db: DbSession,
    storage: DirectoryStorage,
    source: Video,
    orders: list[list[int]],
    lock_last: bool,
    renumber_text: bool,
    user_id: int,
    pinned=(),
) -> tuple[list[Video], bool, list[str]]:
    """One copy per order, all or none: a failure removes the files of the copies made before it (their rows go with
    the request's rollback)."""
    scenes = check_orders(db, source, orders, lock_last, pinned)
    title, _ = split_scenes(db, source)
    renumbering, warnings = numbered(scenes) if renumber_text else (False, [])
    if renumber_text and not renumbering:
        warnings.append("Không phát hiện đánh số ở đầu chữ các cảnh, giữ nguyên chữ")
    root = _root_id(source)
    made = db.scalar(select(func.count()).select_from(Video).where(Video.shuffled_from_id == root)) or 0
    base = video_name(source, title)
    keys = {scene.id: _key(scene) for scene in scenes}
    copies: list[Video] = []
    try:
        for index, order in enumerate(orders, start=made + 1):
            draft, copied = copy_video(db, storage, source, user_id, with_suffix(base, f" (xáo {index})"))
            copies.append(draft)
            by_source = {scene.id: copied[scene.id] for scene in scenes}
            for scene in [title, *scenes]:
                if scene is not None:
                    copied[scene.id].source_scene_id = _key(scene)
            _apply([by_source[scene_id] for scene_id in order], renumbering)
            draft.shuffled_from_id = root
            draft.scene_order = _signature(keys[scene_id] for scene_id in order)
            draft.review_title = title_of(source, title) or None
        db.flush()
    except BaseException:
        for draft in copies:
            storage.delete_prefix(f"videos/{draft.id}")
        raise
    return copies, renumbering, warnings


def reshuffle(
    db: DbSession, video: Video, lock_last: bool, renumber_text: bool, order: list[int] | None = None, pinned=()
) -> list[int]:
    """ "Xáo lại cảnh" on a copy: another order than its own and its siblings', or `order` (its previous one, for
    "Hoàn tác"). Returns the order it had before."""
    _, scenes = split_scenes(db, video)
    previous = [scene.id for scene in scenes]
    if order is None:
        taken = _taken(db, _root_id(video), {_key(scene): scene.id for scene in scenes})
        locked = _locked(scenes, lock_last, pinned)
        found = generate_orders(previous, locked, 1, taken) or generate_orders(previous, locked, 1)
        if not found:
            raise ApiError(409, "nothing_to_shuffle", "Cần ít nhất 2 cảnh xáo được")
        order = found[0]
    elif sorted(order) != sorted(previous):
        raise ApiError(409, "scenes_changed", "Cảnh của video vừa thay đổi, không hoàn tác được")
    by_id = {scene.id: scene for scene in scenes}
    renumbering = renumber_text and numbered(scenes)[0]
    _apply([by_id[scene_id] for scene_id in order], renumbering)
    video.scene_order = _signature(_key(by_id[scene_id]) for scene_id in order)
    return previous
