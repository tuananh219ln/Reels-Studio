"""Shopee's Custom Link file: the export (docs/decisions/2026-11-24-custom-link-excel.md)."""

import io

import pytest
from conftest import first_topic, login, make_user
from openpyxl import load_workbook

from reels_api.models import AffiliateProduct, Fanpage, KnowledgeTopic

EXPORT = "/api/affiliate-products/custom-link/export.xlsx"
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
    got = rows(an.get(EXPORT, params={"topic_id": topic.id}))
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


def test_a_group_with_two_pages_is_refused_rather_than_measured_wrong(an, db, me):
    topic = first_topic(db)
    page(db, topic, "Page A")
    page(db, topic, "Page B")
    page(db, topic, "Page C", active=False)
    product(db, me, topic, 1)
    response = an.get(EXPORT, params={"topic_id": topic.id})
    assert response.status_code == 422
    assert "2 Page" in response.json()["message"]


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
