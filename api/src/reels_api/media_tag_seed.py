"""The one-off tagging of the Già Mà Khỏe photos (Ông Khỏe – Bà Vui, loaded on 2026-11-11 as media ids 25–66),
by file name, from the table of docs/specs/media-tags/brief.md: `python -m reels_api seed-media-tags` (add
`--dry-run` to only read). Run by a person, once; running it again adds nothing, as a tag an item already has is
never added twice, and a tag a member gave it stays. An item whose name is not in the table is left as it is and
named in the log (docs/decisions/2026-11-11-media-tags.md)."""

from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import MediaItem

TAGS: dict[str, tuple[str, ...]] = {
    "gia-goi-01-mo-dau.webp": ("ca-hai", "phong-khach", "ngoi-ghe", "mo-dau", "nam-tay"),
    "gia-goi-02-nang-chan-thang.webp": ("ba", "phong-khach", "ngoi-ghe", "nang-chan-thang", "goi", "dui-truoc"),
    "gia-goi-03-truot-got.webp": ("ba", "phong-khach", "ngoi-ghe", "truot-got", "goi"),
    "gia-goi-04-ep-goi-xuong-khan.webp": ("ong", "phong-khach", "ngoi-ghe", "ep-goi", "khan", "goi", "dui-truoc"),
    "gia-goi-05-nhac-got-chan.webp": ("ba", "phong-khach", "ngoi-ghe", "nhac-got", "bap-chan", "co-chan"),
    "gia-goi-06-xoay-co-chan.webp": ("ong", "phong-khach", "ngoi-ghe", "xoay-co-chan", "co-chan"),
    "gia-goi-07-nghi-uong-nuoc.webp": ("ca-hai", "phong-khach", "ngoi-ghe", "nghi", "uong-nuoc", "luu-y"),
    "gia-goi-08-cta-nam-tay.webp": ("ca-hai", "phong-khach", "ngoi-ghe", "cta", "nam-tay"),
    "gia-goi-09-xoa-bop-goi.webp": ("ba", "phong-ngu", "ngoi-me-giuong", "xoa-bop", "goi", "buoi-toi"),
    "gia-goi-10-chuom-am-goi.webp": ("ong", "phong-ngu", "ngoi-ghe", "chuom-am", "khan", "goi", "buoi-toi"),
    "gia-ngu-01-mo-dau.webp": ("ca-hai", "phong-ngu", "ngoi-tren-giuong", "mo-dau", "buoi-toi"),
    "gia-ngu-02-tho-bung.webp": ("ong", "phong-ngu", "nam-ngua", "tho-bung", "hoi-tho"),
    "gia-ngu-03-om-goi.webp": ("ong", "phong-ngu", "nam-ngua", "om-goi", "lung-duoi", "hong"),
    "gia-ngu-04-van-minh.webp": ("ba", "phong-ngu", "nam-ngua", "van-minh", "cot-song"),
    "gia-ngu-05-gac-chan-len-goi.webp": ("ba", "phong-ngu", "nam-ngua", "gac-chan", "thu-gian"),
    "gia-ngu-06-tha-long.webp": ("ca-hai", "phong-ngu", "nam", "tha-long", "toan-than"),
    "gia-ngu-07-ngoi-me-giuong.webp": ("ong", "phong-ngu", "ngoi-me-giuong", "luu-y", "chong-mat"),
    "gia-ngu-08-cta.webp": ("ca-hai", "phong-ngu", "ngoi-tren-giuong", "cta", "vay-tay"),
    "gia-ngu-09-xoay-co.webp": ("ong", "phong-ngu", "ngoi-me-giuong", "xoay-co", "co"),
    "gia-ngu-10-nhun-vai.webp": ("ba", "phong-ngu", "ngoi-me-giuong", "nhun-vai", "vai"),
    "gia-ngu-11-vuon-tay.webp": ("ong", "phong-ngu", "ngoi-me-giuong", "vuon-tay", "vai", "dan-tay"),
    "gia-ngu-12-xoay-co-tay-co-chan.webp": (
        "ba",
        "phong-ngu",
        "ngoi-me-giuong",
        "xoay-co-tay",
        "xoay-co-chan",
        "co-tay",
        "co-chan",
    ),
    "gia-sofa-01-xoay-co.webp": ("ong", "sofa", "ngoi", "xoay-co", "co", "xem-tivi", "buoi-toi"),
    "gia-sofa-02-nhun-vai.webp": ("ba", "sofa", "ngoi", "nhun-vai", "vai", "xem-tivi", "buoi-toi"),
    "gia-sofa-03-xoay-co-tay.webp": ("ong", "sofa", "ngoi", "xoay-co-tay", "co-tay", "xem-tivi", "buoi-toi"),
    "gia-sofa-04-vuon-tay.webp": ("ba", "sofa", "ngoi", "vuon-tay", "vai", "dan-tay", "xem-tivi", "buoi-toi"),
    "gia-dung-01-nhon-chan-vin-ghe.webp": (
        "ong",
        "phong-khach",
        "dung",
        "vin-ghe",
        "nhon-chan",
        "bap-chan",
        "thang-bang",
    ),
    "gia-dung-02-dung-mot-chan.webp": ("ba", "phong-khach", "dung", "vin-ghe", "dung-mot-chan", "thang-bang"),
    "gia-dung-03-buoc-ngang.webp": ("ong", "phong-khach", "dung", "vin-ghe", "buoc-ngang", "hong", "thang-bang"),
    "gia-dung-04-got-cham-mui.webp": ("ba", "phong-khach", "dung", "vin-ghe", "got-cham-mui", "tandem", "thang-bang"),
    "gia-lung-01-om-mot-goi.webp": ("ong", "phong-ngu", "nam-ngua", "om-mot-goi", "lung-duoi"),
    "gia-lung-02-nam-nghieng-om-goi-om.webp": ("ba", "phong-ngu", "nam-nghieng", "om-goi-om", "lung", "thu-gian"),
    "gia-lung-03-tuong-truot.webp": ("ong", "tuong", "dung", "truot-tuong", "lung", "dui"),
    "gia-lung-04-tuong-vuon-tay.webp": ("ba", "tuong", "dung", "vuon-tay", "lung-tren", "vai"),
    "gia-lung-05-tuong-ep-lung.webp": ("ba", "tuong", "dung", "ep-lung", "lung-duoi", "chong-hong"),
    "gia-lung-06-tuong-nang-goi.webp": ("ong", "tuong", "dung", "vin-tuong", "nang-goi", "hong"),
    "gia-trinho-01-cham-cheo.webp": ("ong", "phong-khach", "dung", "cham-cheo", "phoi-hop", "tri-nho"),
    "gia-trinho-02-dem-ngon-tay.webp": ("ba", "phong-khach", "ngoi-ban", "dem-ngon-tay", "ngon-tay", "tri-nho"),
    "gia-tay-01-nam-mo.webp": ("ong", "phong-khach", "ngoi-ghe", "nam-mo", "ban-tay", "ngon-tay", "khop-tay"),
    "gia-tay-02-xoa-bop-ngon.webp": ("ba", "phong-khach", "ngoi-ghe", "xoa-bop", "ngon-tay", "khop-tay"),
    "gia-dibo-01-tu-the-dung.webp": ("ca-hai", "vuon", "di-bo", "tu-the-dung", "toan-than"),
    "gia-dibo-02-gu-lung.webp": ("ong", "vuon", "di-bo", "tu-the-sai", "gu-lung", "canh-bao"),
}


def _stem(name: str) -> str:
    """A file name without its extension, lowercase: the table's "gia-goi-01-mo-dau.webp" also finds a .jpg copy."""
    return PurePosixPath(name.strip()).stem.lower()


def apply(db: DbSession, dry_run: bool = False) -> list[str]:
    """Adds each photo's tags from the table to the items of that name; returns the log, one line per change."""
    wanted = {_stem(name): (name, tags) for name, tags in TAGS.items()}
    log: list[str] = []
    found: set[str] = set()
    changed = 0
    for item in db.scalars(select(MediaItem).order_by(MediaItem.id).with_for_update()):
        row = wanted.get(_stem(item.name))
        if row is None:
            log.append(f"Bỏ qua #{item.id} “{item.name}”: không có trong bảng thẻ")
            continue
        found.add(row[0])
        before = list(item.tags or [])
        after = list(dict.fromkeys([*before, *row[1]]))
        if after == before:
            log.append(f"Giữ nguyên #{item.id} “{item.name}”: đã đủ thẻ")
            continue
        changed += 1
        added = [tag for tag in after if tag not in before]
        log.append(f"Thêm thẻ #{item.id} “{item.name}”: {', '.join(added)}")
        if not dry_run:
            item.tags = after
    for name in TAGS:
        if name not in found:
            log.append(f"Không thấy ảnh “{name}” trong kho")
    log.append(
        f"{'Chạy thử: ' if dry_run else ''}{changed} ảnh thêm thẻ, {len(found)}/{len(TAGS)} ảnh trong bảng có trong kho"
    )
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return log
