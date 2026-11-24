"""Shopee's "Custom Link" by Excel (docs/decisions/2026-11-24-custom-link-excel.md): without Shopee's Open API the tool
cannot turn a product page into an affiliate link, so it writes the file Shopee's Custom Link page takes (one product
page per row, `Sub_id1` = the Page, so an order names its Page: affiliate_rounds.read_orders), a member uploads it
there once and brings the result back."""

import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .models import AffiliateProduct, Fanpage, KnowledgeTopic, Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/affiliate-products/custom-link")

# Shopee's template: one header row, in this order.
EXPORT_HEADERS = ("Liên kết gốc", "Sub_id1", "Sub_id2", "Sub_id3", "Sub_id4", "Sub_id5")
MAX_LINKS = 10_000  # what Shopee takes in one upload
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def group_page(db: DbSession, topic_id: int) -> Fanpage:
    """The one Page that posts the group. An order carries only that Page, so with two the orders of the other would
    be counted on the first: refused rather than measured wrong."""
    if db.get(KnowledgeTopic, topic_id) is None:
        raise invalid("Nhóm chủ đề không còn tồn tại")
    pages = list(
        db.scalars(
            select(Fanpage).where(Fanpage.knowledge_topic_id == topic_id, Fanpage.active.is_(True)).order_by(Fanpage.id)
        )
    )
    if not pages:
        raise invalid("Nhóm này chưa có Page nào đăng, nên chưa biết gắn đơn về Page nào")
    if len(pages) > 1:
        names = ", ".join(page.name for page in pages)
        raise invalid(f"Nhóm này có {len(pages)} Page đăng ({names}): đơn chỉ đo được về một Page, hãy tách nhóm")
    return pages[0]


@router.get("/export.xlsx")
def export_file(
    topic_id: int,
    include_linked: bool = False,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> Response:
    """The group's approved products I added, with a product page, as Shopee's Custom Link file. Without
    `include_linked` only the ones with no affiliate link yet; a teammate's are left out, as their link is theirs."""
    page = group_page(db, topic_id)
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
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Custom Link")
    sheet.append(list(EXPORT_HEADERS))
    for link in links:
        sheet.append([link, f"p{page.id}", None, None, None, None])
    out = io.BytesIO()
    workbook.save(out)
    headers = {"Content-Disposition": f'attachment; filename="custom-link-nhom-{topic_id}.xlsx"'}
    return Response(out.getvalue(), media_type=XLSX, headers=headers)
