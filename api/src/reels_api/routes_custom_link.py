"""Shopee's "Custom Link" by Excel (docs/decisions/2026-11-24-custom-link-excel.md): without Shopee's Open API the tool
cannot turn a product page into an affiliate link, so it writes the file Shopee's Custom Link page takes (one product
page per row, `Sub_id1` = the Page, so an order names its Page: affiliate_rounds.read_orders), a member uploads it
there once and brings the result back."""

import csv
import io
import re
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import affiliate
from .db import get_db
from .models import AffiliateProduct, Fanpage, KnowledgeTopic, Session
from .routes_affiliate import MAX_URL_LENGTH, _clear_approval
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/affiliate-products/custom-link")

# Shopee's template: one header row, in this order.
EXPORT_HEADERS = ("Liên kết gốc", "Sub_id1", "Sub_id2", "Sub_id3", "Sub_id4", "Sub_id5")
MAX_LINKS = 10_000  # what Shopee takes in one upload
MAX_FILE_BYTES = 5_000_000
# What a header of the original-link column may say (Shopee's template: "Liên kết gốc").
ORIGINAL_HEADERS = ("liên kết gốc", "link gốc", "original link", "original url")
# Where a converted link points: Shopee's short link hosts.
SHORT_HOSTS = ("shopee.vn", "shope.ee", "shp.ee")
# A product page names its shop and item: ".../product/{shop}/{item}" or "...-i.{shop}.{item}".
ITEM_IN_URL = re.compile(r"(?:/product/|-i\.)(\d+)[/.](\d+)")
# Shopee's own template file: it refuses a workbook built from scratch ("sử dụng bản mẫu có sẵn"), so rows are added to a
# copy of it (its sheet name "Sheet1" and document properties stay).
TEMPLATE = Path(__file__).with_name("custom_link_template.xlsx")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def group_page(db: DbSession, topic_id: int, fanpage_id: int | None = None) -> Fanpage:
    """The Page the file's orders are measured to: the group's only Page, or, when several post it, the one chosen. An
    order carries one Page, and a product has one link, so the orders of the others are not measured to them."""
    if db.get(KnowledgeTopic, topic_id) is None:
        raise invalid("Nhóm chủ đề không còn tồn tại")
    pages = list(
        db.scalars(
            select(Fanpage).where(Fanpage.knowledge_topic_id == topic_id, Fanpage.active.is_(True)).order_by(Fanpage.id)
        )
    )
    if not pages:
        raise invalid("Nhóm này chưa có Page nào đăng, nên chưa biết gắn đơn về Page nào")
    if fanpage_id is None:
        if len(pages) > 1:
            names = ", ".join(page.name for page in pages)
            raise invalid(f"Nhóm này có {len(pages)} Page đăng ({names}): hãy chọn Page để gắn đơn về")
        return pages[0]
    chosen = next((page for page in pages if page.id == fanpage_id), None)
    if chosen is None:
        raise invalid("Page này không đăng nhóm này")
    return chosen


@router.get("/export.xlsx")
def export_file(
    topic_id: int,
    include_linked: bool = False,
    fanpage_id: int | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> Response:
    """The group's approved products I added, with a product page, as Shopee's Custom Link file. Without
    `include_linked` only the ones with no affiliate link yet; a teammate's are left out, as their link is theirs."""
    page = group_page(db, topic_id, fanpage_id)
    query = select(AffiliateProduct.page_url).where(
        AffiliateProduct.knowledge_topic_id == topic_id,
        AffiliateProduct.created_by_id == me.user_id,
        AffiliateProduct.status == "approved",
        AffiliateProduct.page_url.is_not(None),
        AffiliateProduct.page_url != "",
    )
    if not include_linked:
        query = query.where((AffiliateProduct.url.is_(None)) | (AffiliateProduct.url == ""))
    links = list(dict.fromkeys(db.scalars(query.order_by(AffiliateProduct.id))))  # one row per product page
    if not links:
        raise invalid("Không có sản phẩm nào cần xuất: cần sản phẩm đã duyệt, của bạn, có link sản phẩm")
    if len(links) > MAX_LINKS:
        raise invalid(f"Shopee nhận tối đa {MAX_LINKS} link mỗi lần, nhóm này có {len(links)}")
    workbook = load_workbook(TEMPLATE)
    sheet = workbook.worksheets[0]
    for link in links:
        sheet.append([link, f"p{page.id}", None, None, None, None])
    out = io.BytesIO()
    workbook.save(out)
    headers = {"Content-Disposition": f'attachment; filename="custom-link-nhom-{topic_id}.xlsx"'}
    return Response(out.getvalue(), media_type=XLSX, headers=headers)


def page_key(url: str) -> str:
    """A product page as one string: the shop and item when the address names them (so a tracking tail or a slug does
    not matter), else the address without scheme, query, fragment and trailing slash."""
    parts = urlsplit(url.strip())
    found = ITEM_IN_URL.search(parts.path)
    if found:
        return f"item:{found.group(1)}.{found.group(2)}"
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}".lower()


def _is_short_link(value: object) -> bool:
    if not isinstance(value, str) or any(char.isspace() for char in value.strip()):
        return False
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return False
    host = parts.netloc.lower()
    return parts.scheme in ("http", "https") and any(host == name or host.endswith(f".{name}") for name in SHORT_HOSTS)


def _header(cell: object) -> str:
    return " ".join(unicodedata.normalize("NFC", str(cell or "")).lower().split())


CONVERTED_HEADERS = ("liên kết chuyển đổi", "converted link", "converted url")
REASON_HEADERS = ("lí do thất bại", "lý do thất bại", "failure reason", "reason")


def _table(data: bytes) -> list[list[object]]:
    """The file's rows: Shopee hands the result back as CSV (BOM, comma), a member may save it as Excel."""
    if data[:2] == b"PK":
        try:
            sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
            return [list(row) for row in sheet.iter_rows(values_only=True)]
        except (zipfile.BadZipFile, KeyError, ValueError, IndexError, OSError):
            raise invalid("File Excel không đọc được") from None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise invalid("File không đọc được: cần file CSV (UTF-8) hoặc Excel (.xlsx) Shopee trả về") from None
    try:
        dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def _column(headers: list[str], names: tuple[str, ...]) -> int | None:
    return next((index for index, name in enumerate(headers) if name in names), None)


def parsed_file(data: bytes) -> list[tuple[int, str, str | None, str]]:
    """The file's rows as (row number, original link, converted link or None, why Shopee failed it). Columns by the
    names Shopee's result file has ("Liên kết gốc", "Liên kết chuyển đổi", "Lí do thất bại"); without a named
    converted-link column, the other cell of the row that is a Shopee link."""
    if len(data) > MAX_FILE_BYTES:
        raise invalid("File quá lớn, hãy chia nhỏ")
    table = _table(data)
    if not table:
        raise invalid("File trống")
    headers = [_header(cell) for cell in table[0]]
    original = _column(headers, ORIGINAL_HEADERS)
    if original is None:
        shown = ", ".join(name for name in headers if name) or "không có tiêu đề"
        raise invalid(f"Không thấy cột “Liên kết gốc” (các cột có: {shown}). Hãy dùng file Shopee trả về")
    named = _column(headers, CONVERTED_HEADERS)
    reason_at = _column(headers, REASON_HEADERS)
    rows = []
    for number, row in enumerate(table[1:], start=2):
        cells = list(row)
        link = cells[original] if original < len(cells) else None
        if not isinstance(link, str) or not link.strip():
            continue
        if named is not None:
            cell = cells[named] if named < len(cells) else None
            converted = str(cell).strip() if _is_short_link(cell) else None
        else:
            converted = next(
                (str(cell).strip() for index, cell in enumerate(cells) if index != original and _is_short_link(cell)),
                None,
            )
        why = cells[reason_at] if reason_at is not None and reason_at < len(cells) else None
        rows.append((number, link.strip(), converted, str(why).strip() if why else ""))
    if not rows:
        raise invalid("File không có dòng nào")
    if len(rows) > MAX_LINKS:
        raise invalid(f"Mỗi lần nhập tối đa {MAX_LINKS} link")
    return rows


def _matched(db: DbSession, topic_id: int, user_id: int, rows: list[tuple[int, str, str | None, str]]) -> list[dict]:
    """Each row with what the import would do: "ok" (a product I added in this group), "others" (only a teammate's has
    this page: their link stays), or an error. A teammate's product is never written, whatever the file says."""
    products = list(
        db.scalars(
            select(AffiliateProduct).where(
                AffiliateProduct.knowledge_topic_id == topic_id, AffiliateProduct.page_url.is_not(None)
            )
        )
    )
    mine: dict[str, list[AffiliateProduct]] = {}
    theirs: dict[str, AffiliateProduct] = {}
    for product in products:
        key = page_key(product.page_url)
        if product.created_by_id == user_id:
            mine.setdefault(key, []).append(product)
        else:
            theirs.setdefault(key, product)
    result = []
    seen: set[str] = set()
    for number, link, converted, why in rows:
        key = page_key(link)
        row = {"row": number, "original": link, "link": converted, "state": "error", "message": "", "ids": []}
        if key in seen:
            row["message"] = "Link gốc trùng với một dòng phía trên"
        elif converted is None:
            row["message"] = (
                f"Shopee không chuyển đổi được: {why}" if why else "Link chuyển đổi trống hoặc không phải link Shopee"
            )
        elif len(converted) > MAX_URL_LENGTH:
            row["message"] = f"Link chuyển đổi dài quá {MAX_URL_LENGTH} ký tự"
        elif key in mine:
            row["state"], row["ids"] = "ok", [product.id for product in mine[key]]
            row["name"] = mine[key][0].name
        elif key in theirs:
            owner = theirs[key].created_by.name
            row["state"], row["name"] = "others", theirs[key].name
            row["message"] = f"Sản phẩm của {owner}, link của họ được giữ nguyên"
        else:
            row["message"] = "Link gốc không khớp sản phẩm nào của bạn trong nhóm này"
        if row["state"] != "error":
            seen.add(key)  # a failed row does not hide a later good one of the same page
        result.append(row)
    return result


def _summary(rows: list[dict]) -> dict:
    return {
        "rows": rows,
        "ok": sum(row["state"] == "ok" for row in rows),
        "others": sum(row["state"] == "others" for row in rows),
        "errors": sum(row["state"] == "error" for row in rows),
    }


async def _read(file: UploadFile, topic_id: int, me: Session, db: DbSession) -> list[dict]:
    if db.get(KnowledgeTopic, topic_id) is None:
        raise invalid("Nhóm chủ đề không còn tồn tại")
    data = await file.read(MAX_FILE_BYTES + 1)
    return _matched(db, topic_id, me.user_id, parsed_file(data))


@router.post("/import/preview")
async def preview_import(
    knowledge_topic_id: int = Form(),
    file: UploadFile = File(),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """What "Nhập" would do with Shopee's result file, row by row; writes nothing."""
    return _summary(await _read(file, knowledge_topic_id, me, db))


@router.post("/import")
async def import_file(
    knowledge_topic_id: int = Form(),
    file: UploadFile = File(),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """Puts each converted link on the matching product I added in the group: an approved one stays approved unless it
    no longer meets the rules, and comments already written under live posts are asked to follow the new link."""
    rows = await _read(file, knowledge_topic_id, me, db)
    changed: list[int] = []
    for row in rows:
        if row["state"] != "ok":
            continue
        for product in db.scalars(select(AffiliateProduct).where(AffiliateProduct.id.in_(row["ids"]))):
            if product.url == row["link"]:
                continue
            product.url = row["link"]
            if product.status == "approved" and affiliate.problems(product):
                _clear_approval(product)
            changed.append(product.id)
    affiliate.ask_comment_refresh(db, changed, forget_links=True)
    db.commit()
    return {**_summary(rows), "linked": len(changed)}
