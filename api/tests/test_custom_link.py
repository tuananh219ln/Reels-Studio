"""Shopee's Custom Link file: the export (docs/decisions/2026-11-24-custom-link-excel.md)."""

import io

import pytest
from conftest import first_topic, login, make_user
from openpyxl import Workbook, load_workbook

from reels_api.models import AffiliateProduct, Fanpage, KnowledgeTopic

EXPORT = "/api/affiliate-products/custom-link/export.xlsx"
PREVIEW = "/api/affiliate-products/custom-link/import/preview"
IMPORT = "/api/affiliate-products/custom-link/import"
HEADERS = ["Liên kết gốc", "Sub_id1", "Sub_id2", "Sub_id3", "Sub_id4", "Sub_id5"]


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def page(db, topic, name="Page A", active=True) -> Fanpage:
    row = Fanpage(
        page_id=f"fb-{name}", name=name, token_encrypted="x", token_tail="x", knowledge_topic_id=topic.id, active=active
    )
    db.add(row)
    db.commit()
    return row


def product(db, user, topic, n, **fields) -> AffiliateProduct:
    values = {
        "knowledge_topic_id": topic.id,
        "name": f"Món {n}",
        "page_url": f"https://shopee.vn/product/1/{n}",
        "url": None,
        "shop_name": "Shop",
        "shop_type": "mall",
        "rating": 4.8,
        "sold": 500,
        "price": 100000,
        "commission_rate": 10,
        "status": "approved",
        "created_by_id": user.id,
        **fields,
    }
    row = AffiliateProduct(**values)
    db.add(row)
    db.commit()
    return row


def rows(response) -> list[list]:
    assert response.status_code == 200, response.text
    sheet = load_workbook(io.BytesIO(response.content)).active
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def test_the_file_has_shopees_header_and_one_row_per_product_with_the_page_as_sub_id1(an, db, me):
    topic = first_topic(db)
    target = page(db, topic)
    product(db, me, topic, 1)
    product(db, me, topic, 2)
    response = an.get(EXPORT, params={"topic_id": topic.id})
    # Shopee refuses a workbook that is not its template: same sheet name and document properties.
    book = load_workbook(io.BytesIO(response.content))
    assert book.sheetnames == ["Sheet1"]
    assert [prop.name for prop in book.custom_doc_props.props] == ["KSOProductBuildVer"]
    got = rows(response)
    assert got[0] == HEADERS
    assert got[1:] == [
        ["https://shopee.vn/product/1/1", f"p{target.id}", None, None, None, None],
        ["https://shopee.vn/product/1/2", f"p{target.id}", None, None, None, None],
    ]


def test_only_approved_products_of_mine_with_a_product_page_and_no_link_yet(an, db, me):
    topic = first_topic(db)
    page(db, topic)
    other = make_user(db, email="binh@doi.vn", name="Bình")
    product(db, me, topic, 1)
    product(db, me, topic, 2, status="draft")
    product(db, me, topic, 3, page_url=None, url="https://s.shopee.vn/x")
    product(db, me, topic, 4, url="https://s.shopee.vn/has-link")
    product(db, other, topic, 5)
    other_topic = KnowledgeTopic(name="Nhóm khác", created_by_id=me.id)
    db.add(other_topic)
    db.commit()
    product(db, me, other_topic, 6)
    got = rows(an.get(EXPORT, params={"topic_id": topic.id}))
    assert [row[0] for row in got[1:]] == ["https://shopee.vn/product/1/1"]


def test_include_linked_adds_the_products_that_already_have_a_link(an, db, me):
    topic = first_topic(db)
    page(db, topic)
    product(db, me, topic, 1)
    product(db, me, topic, 2, url="https://s.shopee.vn/has-link")
    got = rows(an.get(EXPORT, params={"topic_id": topic.id, "include_linked": True}))
    assert [row[0] for row in got[1:]] == ["https://shopee.vn/product/1/1", "https://shopee.vn/product/1/2"]


def test_a_product_page_listed_twice_is_one_row(an, db, me):
    topic = first_topic(db)
    page(db, topic)
    product(db, me, topic, 1)
    product(db, me, topic, 1)
    assert len(rows(an.get(EXPORT, params={"topic_id": topic.id}))) == 2


def test_a_group_without_a_page_is_refused(an, db, me):
    topic = first_topic(db)
    product(db, me, topic, 1)
    response = an.get(EXPORT, params={"topic_id": topic.id})
    assert response.status_code == 422
    assert "chưa có Page" in response.json()["message"]


def test_a_group_with_two_pages_asks_which_one_and_uses_the_chosen(an, db, me):
    topic = first_topic(db)
    a = page(db, topic, "Page A")
    b = page(db, topic, "Page B")
    page(db, topic, "Page C", active=False)
    product(db, me, topic, 1)
    asked = an.get(EXPORT, params={"topic_id": topic.id})
    assert asked.status_code == 422
    assert "chọn Page" in asked.json()["message"]
    got = rows(an.get(EXPORT, params={"topic_id": topic.id, "fanpage_id": b.id}))
    assert got[1][1] == f"p{b.id}"
    assert a.id != b.id


def test_a_page_that_does_not_post_the_group_is_refused(an, db, me):
    topic = first_topic(db)
    page(db, topic, "Page A")
    page(db, topic, "Page B")
    elsewhere = KnowledgeTopic(name="Nhóm khác", created_by_id=me.id)
    db.add(elsewhere)
    db.commit()
    stranger = page(db, elsewhere, "Page lạ")
    product(db, me, topic, 1)
    response = an.get(EXPORT, params={"topic_id": topic.id, "fanpage_id": stranger.id})
    assert response.status_code == 422
    assert "không đăng nhóm này" in response.json()["message"]


def test_one_page_is_used_without_being_asked(an, db, me):
    topic = first_topic(db)
    only = page(db, topic, "Page A")
    product(db, me, topic, 1)
    assert rows(an.get(EXPORT, params={"topic_id": topic.id}))[1][1] == f"p{only.id}"


def test_nothing_to_export_is_said(an, db, me):
    topic = first_topic(db)
    page(db, topic)
    response = an.get(EXPORT, params={"topic_id": topic.id})
    assert response.status_code == 422
    assert "Không có sản phẩm" in response.json()["message"]


def test_more_than_the_shopee_limit_is_refused(an, db, me, monkeypatch):
    from reels_api import routes_custom_link

    topic = first_topic(db)
    page(db, topic)
    product(db, me, topic, 1)
    product(db, me, topic, 2)
    monkeypatch.setattr(routes_custom_link, "MAX_LINKS", 1)
    response = an.get(EXPORT, params={"topic_id": topic.id})
    assert response.status_code == 422
    assert "tối đa 1" in response.json()["message"]


def test_a_visitor_is_sent_to_login(client, db):
    assert client.get(EXPORT, params={"topic_id": first_topic(db).id}).status_code == 401


def result_file(*rows, header=("Liên kết gốc", "Sub_id1", "Liên kết đã chuyển đổi")) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(header))
    for row in rows:
        sheet.append(list(row))
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def send(an, db, url, data, topic=None):
    files = {"file": ("ket-qua.xlsx", data, XLSX)}
    return an.post(url, data={"knowledge_topic_id": (topic or first_topic(db)).id}, files=files)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHORT = "https://s.shopee.vn/AbC"


def test_preview_matches_by_shop_and_item_and_writes_nothing(an, db, me):
    topic = first_topic(db)
    mine = product(db, me, topic, 1)
    data = result_file(("https://shopee.vn/ten-san-pham-i.1.1?sp_atk=xyz", "p1", SHORT))
    got = send(an, db, PREVIEW, data).json()
    assert (got["ok"], got["others"], got["errors"]) == (1, 0, 0)
    assert got["rows"][0]["ids"] == [mine.id]
    db.refresh(mine)
    assert mine.url is None


def test_import_puts_the_link_on_my_product_and_keeps_its_approval(an, db, me):
    topic = first_topic(db)
    mine = product(db, me, topic, 1)
    got = send(an, db, IMPORT, result_file((mine.page_url, "p1", SHORT)))
    assert got.status_code == 200, got.text
    assert got.json()["linked"] == 1
    db.refresh(mine)
    assert (mine.url, mine.status) == (SHORT, "approved")


def test_a_teammates_product_keeps_its_link_and_is_listed_as_others(an, db, me):
    topic = first_topic(db)
    other = make_user(db, email="binh@doi.vn", name="Bình")
    theirs = product(db, other, topic, 2, url="https://s.shopee.vn/theirs")
    got = send(an, db, IMPORT, result_file((theirs.page_url, "p1", SHORT))).json()
    assert (got["ok"], got["others"], got["linked"]) == (0, 1, 0)
    assert "Bình" in got["rows"][0]["message"]
    db.refresh(theirs)
    assert theirs.url == "https://s.shopee.vn/theirs"


def test_each_bad_row_says_why(an, db, me):
    topic = first_topic(db)
    mine = product(db, me, topic, 1)
    data = result_file(
        ("https://shopee.vn/product/9/9", "p1", SHORT),
        (mine.page_url, "p1", None),
        (mine.page_url, "p1", "not a link"),
    )
    got = send(an, db, PREVIEW, data).json()
    assert got["errors"] == 3
    assert "không khớp" in got["rows"][0]["message"]
    assert "Link chuyển đổi trống" in got["rows"][1]["message"]
    assert "Link chuyển đổi trống" in got["rows"][2]["message"]


def test_a_page_listed_twice_takes_the_first_row_only(an, db, me):
    topic = first_topic(db)
    mine = product(db, me, topic, 1)
    got = send(
        an, db, IMPORT, result_file((mine.page_url, "p1", SHORT), (mine.page_url, "p1", "https://s.shopee.vn/2"))
    )
    body = got.json()
    assert (body["linked"], body["errors"]) == (1, 1)
    assert "trùng" in body["rows"][1]["message"]
    db.refresh(mine)
    assert mine.url == SHORT


def test_a_file_that_is_not_excel_or_lacks_the_original_column_is_refused(an, db, me):
    refused = send(an, db, PREVIEW, b"khong phai excel")
    assert refused.status_code == 422
    assert "Liên kết gốc" in refused.json()["message"]
    broken = send(an, db, PREVIEW, b"PK\x03\x04junk")
    assert broken.status_code == 422
    assert "Excel không đọc được" in broken.json()["message"]
    wrong = send(an, db, PREVIEW, result_file(("a", "b"), header=("Tên", "Giá")))
    assert wrong.status_code == 422
    assert "Liên kết gốc" in wrong.json()["message"]
    assert "tên, giá" in wrong.json()["message"]


# What Shopee's Custom Link page really returned (24/11/2026): a CSV with a BOM, the template's six columns, then the
# converted link and why a row failed.
SHOPEE_RESULT = (
    "\ufeffLiên kết gốc,Sub_id1,Sub_id2,Sub_id3,Sub_id4,Sub_id5,Liên kết chuyển đổi,Lí do thất bại\n"
    "https://shopee.vn/product/1/1,p1,,,,,https://s.shopee.vn/8pnbffRIIN,\n"
    "https://shopee.vn/product/1/2,p1,,,,,,Liên kết không hợp lệ\n"
).encode()


def test_shopees_own_csv_result_is_read_with_its_failure_reason(an, db, me):
    topic = first_topic(db)
    first = product(db, me, topic, 1)
    product(db, me, topic, 2)
    got = send(an, db, IMPORT, SHOPEE_RESULT)
    assert got.status_code == 200, got.text
    body = got.json()
    assert (body["linked"], body["errors"]) == (1, 1)
    assert "Liên kết không hợp lệ" in body["rows"][1]["message"]
    db.refresh(first)
    assert first.url == "https://s.shopee.vn/8pnbffRIIN"
