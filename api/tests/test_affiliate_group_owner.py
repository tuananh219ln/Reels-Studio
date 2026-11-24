"""Only the member who made a topic group adds products to it (docs/decisions/2026-11-25-group-owner-adds-products.md);
the rows already there stay."""

import pytest
from conftest import first_topic, login, make_user

from reels_api.models import AffiliateProduct, KnowledgeTopic

URL = "/api/affiliate-products"


@pytest.fixture
def an(db):
    return make_user(db)


@pytest.fixture
def binh(db):
    return make_user(db, email="binh@doi.vn", name="Trần Thị Bình")


def group(db, maker, name="Nhóm của An") -> KnowledgeTopic:
    topic = KnowledgeTopic(name=name, created_by_id=maker.id if maker else None)
    db.add(topic)
    db.commit()
    return topic


def body(topic, **fields) -> dict:
    return {
        "knowledge_topic_id": topic.id,
        "name": "Vừng đen rang",
        "url": "https://s.shopee.vn/abc",
        "shop_name": "Nhà Vừng",
        "shop_type": "mall",
        "rating": 4.8,
        "sold": 500,
        "price": 100000,
        "commission_rate": 10,
        **fields,
    }


def product(db, user, topic, n=1, **fields) -> AffiliateProduct:
    row = AffiliateProduct(
        knowledge_topic_id=topic.id,
        name=f"Món {n}",
        shopee_item_id=1000 + n,
        page_url=f"https://shopee.vn/product/1/{1000 + n}",
        shop_name="Shop",
        shop_type="mall",
        rating=4.8,
        sold=500,
        price=100000,
        commission_rate=10,
        status="draft",
        created_by_id=user.id,
        **fields,
    )
    db.add(row)
    db.commit()
    return row


def file_row(item_id: int) -> str:
    return (
        "Mã sản phẩm,Tên sản phẩm,Giá,Doanh thu,Tên cửa hàng,Tỉ lệ hoa hồng,Hoa hồng,Link sản phẩm,Link ưu đãi\n"
        f'{item_id},Hạt cải,"45,0k",0,Shop,"2,5%",₫900,https://shopee.vn/product/1/{item_id},\n'
    )


def test_the_maker_adds_by_hand_and_a_teammate_is_refused(client, db, an, binh):
    topic = group(db, an)
    login(client, "binh@doi.vn")
    refused = client.post(URL, json=body(topic))
    assert refused.status_code == 403
    assert "Chỉ người tạo nhóm" in refused.json()["message"]
    login(client, "an@doi.vn")
    assert client.post(URL, json=body(topic)).status_code == 201


def test_a_group_whose_maker_is_unknown_is_open_to_everyone(client, db, binh):
    login(client, "binh@doi.vn")
    assert client.post(URL, json=body(first_topic(db))).status_code == 201


def test_pasted_links_need_the_maker(client, db, an, binh):
    topic = group(db, an)
    login(client, "binh@doi.vn")
    response = client.post(f"{URL}/links", json={"knowledge_topic_id": topic.id, "links": ["https://s.shopee.vn/x"]})
    assert response.status_code == 403


def test_a_file_with_new_rows_is_refused_in_the_preview_and_the_import(client, db, an, binh):
    topic = group(db, an)
    login(client, "binh@doi.vn")
    for path in ("/import/preview", "/import"):
        response = client.post(f"{URL}{path}", json={"knowledge_topic_id": topic.id, "text": file_row(777)})
        assert response.status_code == 403, path
    assert db.query(AffiliateProduct).filter_by(knowledge_topic_id=topic.id).count() == 0


def test_a_teammates_old_row_stays_and_an_import_may_still_update_it(client, db, an, binh):
    topic = group(db, an)
    old = product(db, binh, topic, 5)  # Bình's row from before the rule
    login(client, "binh@doi.vn")
    response = client.post(f"{URL}/import", json={"knowledge_topic_id": topic.id, "text": file_row(1005)})
    assert response.status_code == 201, response.text
    assert response.json()["added"] == 0
    db.refresh(old)
    assert old.created_by_id == binh.id


def test_moving_a_product_into_a_group_of_someone_else_is_refused(client, db, an, binh):
    mine = group(db, binh, "Nhóm của Bình")
    theirs = group(db, an)
    row = product(db, binh, mine)
    login(client, "binh@doi.vn")
    response = client.put(f"{URL}/{row.id}", json=body(theirs, name=row.name))
    assert response.status_code == 403


def test_options_say_which_groups_the_member_may_add_to(client, db, an, binh):
    own = group(db, binh, "Nhóm của Bình")
    other = group(db, an, "Nhóm của An")
    open_group = first_topic(db)
    login(client, "binh@doi.vn")
    topics = {topic["id"]: topic for topic in client.get(f"{URL}/options").json()["topics"]}
    assert topics[own.id]["can_add"] is True
    assert topics[other.id]["can_add"] is False
    assert topics[open_group.id]["can_add"] is True
