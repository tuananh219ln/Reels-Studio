"""Affiliate Shopee: the product list, its approval rule, the CSV, and the products attached to posted reels."""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from conftest import client_for, first_topic, login, make_user, make_video

from reels_api.models import AffiliateProduct, Publication

URL = "/api/affiliate-products"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def body(db, **fields) -> dict:
    return {
        "knowledge_topic_id": first_topic(db).id,
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


def add(an, db, **fields) -> dict:
    response = an.post(URL, json=body(db, **fields))
    assert response.status_code == 201, response.text
    return response.json()


def add_approved(an, db, **fields) -> dict:
    return an.post(f"{URL}/{add(an, db, **fields)['id']}/approve").json()


def posted_video(db, storage, user, status="published", scheduled_at=None, published_at=None, **fields):
    """Like after the publish job, which stamps published_at when the upload ends, even for a scheduled reel."""
    video = make_video(db, storage, user, **fields)
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            status=status,
            remote_id="reel-1",
            scheduled_at=scheduled_at,
            created_by_id=user.id,
            published_at=None if status == "pending" else published_at or datetime.now(UTC),
        )
    )
    db.commit()
    return video


def test_a_new_product_is_a_draft_with_its_expected_commission(an, db):
    product = add(an, db, name="  Vừng   đen ", price=250000, commission_rate=8.5)
    assert product["name"] == "Vừng đen" and product["status"] == "draft"
    assert product["expected_commission"] == 21250 and product["checked_at"] is None
    assert product["shop_type_label"] == "Shopee Mall" and product["topic"] == "Sức khỏe"


def test_list_ranks_by_money_per_order_not_by_percent(an, db):
    # Added best first, so the fallback to the newest row cannot produce the expected order.
    dear = add(an, db, name="Đắt", price=200000, commission_rate=10)
    middle = add(an, db, name="Vừa", price=100000, commission_rate=15)
    cheap = add(an, db, name="Rẻ", price=30000, commission_rate=30)
    assert [row["id"] for row in an.get(URL).json()] == [dear["id"], middle["id"], cheap["id"]]


def test_equal_commission_prefers_mall_then_sales(an, db):
    mall = add(an, db, name="Mall", shop_type="mall", sold=100)
    many = add(an, db, name="Nhiều", shop_type="preferred", sold=900)
    few = add(an, db, name="Ít", shop_type="preferred", sold=200)
    assert [row["id"] for row in an.get(URL).json()] == [mall["id"], many["id"], few["id"]]


def test_the_same_money_on_the_page_is_a_tie_despite_float_rounding(an, db):
    # 100000 * 1.1 is 110000.00000000001 as a double, just above 110000 * 1.
    mall = add(an, db, name="Mall", shop_type="mall", price=110000, commission_rate=1)
    preferred = add(an, db, name="Yêu thích", shop_type="preferred", price=100000, commission_rate=1.1)
    assert preferred["expected_commission"] == mall["expected_commission"]
    assert [row["id"] for row in an.get(URL).json()] == [mall["id"], preferred["id"]]
    # And 200000 * 8.2 falls just below 164000 * 10.
    an.delete(f"{URL}/{mall['id']}")
    an.delete(f"{URL}/{preferred['id']}")
    below = add(an, db, name="Mall 2", shop_type="mall", price=200000, commission_rate=8.2)
    exact = add(an, db, name="Yêu thích 2", shop_type="preferred", price=164000, commission_rate=10)
    assert [row["id"] for row in an.get(URL).json()] == [below["id"], exact["id"]]


def test_list_filters_by_topic_status_and_text(an, db):
    other = an.post("/api/knowledge/topics", json={"name": "Khác"}).json()["topics"][-1]
    sesame = add_approved(an, db, name="100% vừng")
    tea = add(an, db, name="Trà", shop_name="Trà_Việt", knowledge_topic_id=other["id"])

    def ids(query: str) -> list[int]:
        return [row["id"] for row in an.get(f"{URL}{query}").json()]

    assert ids(f"?topic_id={other['id']}") == [tea["id"]]
    assert ids("?status=approved") == [sesame["id"]]
    assert ids("?q=VỪNG") == [sesame["id"]]
    assert ids("?q=trà_") == [tea["id"]]
    assert ids("?q=%25") == [sesame["id"]]


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"name": " "}, "Tên sản phẩm"),
        ({"name": "a" * 301}, "Tên sản phẩm"),
        ({"shop_name": ""}, "Tên shop"),
        ({"url": "javascript:alert(1)"}, "Link phải"),
        ({"url": "s.shopee.vn/abc"}, "Link phải"),
        ({"url": "https://"}, "Link phải"),
        ({"url": "https://[bad"}, "Link phải"),
        ({"url": "https://s.shopee.vn/a b"}, "Link phải"),
        ({"shop_type": "vip"}, "Loại shop"),
        ({"rating": 5.1}, "Số sao"),
        ({"rating": -0.1}, "Số sao"),
        ({"commission_rate": 101}, "Hoa hồng"),
        ({"commission_rate": -1}, "Hoa hồng"),
        ({"price": 0}, "Giá"),
        ({"price": 3_000_000_000}, "Giá"),
        ({"sold": -1}, "Lượt bán"),
        ({"knowledge_topic_id": 999999}, "Nhóm chủ đề"),
    ],
)
def test_a_wrong_form_is_refused(an, db, fields, message):
    response = an.post(URL, json=body(db, **fields))
    assert response.status_code == 422 and message in response.json()["message"]
    assert db.query(AffiliateProduct).count() == 0


def test_approval_records_who_and_when(an, db, me):
    product = add_approved(an, db)
    assert product["status"] == "approved" and product["checked_by"] == me.name and product["checked_at"]


@pytest.mark.parametrize("shop_type", ["mall", "preferred_plus", "preferred"])
def test_a_product_exactly_at_the_bar_can_be_approved(an, db, shop_type):
    product = add_approved(an, db, shop_type=shop_type, rating=4.7, sold=100)
    assert product["status"] == "approved" and product["problems"] == []


def test_banned_words_come_from_the_products_own_topic_group(an, db):
    other = an.post("/api/knowledge/topics", json={"name": "Khác"}).json()["topics"][-1]
    an.patch(f"/api/knowledge/topics/{other['id']}", json={"banned_words": ["siêu rẻ"]})
    assert add(an, db, name="Trà siêu rẻ", knowledge_topic_id=other["id"])["problems"]
    assert add(an, db, name="Trà siêu rẻ")["problems"] == []
    assert add(an, db, name="Trà đặc trị", knowledge_topic_id=other["id"])["problems"] == []


@pytest.mark.parametrize(
    "fields, reason",
    [
        ({"shop_type": "other"}, "Shop phải là"),
        ({"rating": 4.6}, "dưới 4.7 sao"),
        ({"sold": 99}, "dưới 100"),
        ({"name": "Trà đặc trị mất ngủ"}, "đặc trị"),
    ],
)
def test_a_product_below_the_bar_cannot_be_approved(an, db, fields, reason):
    product = add(an, db, **fields)
    assert any(reason in problem for problem in product["problems"])
    refused = an.post(f"{URL}/{product['id']}/approve")
    assert refused.status_code == 409 and reason in refused.json()["message"]
    assert an.get(URL).json()[0]["status"] == "draft"


def test_saving_an_approved_product_unchanged_keeps_its_approval(an, db):
    product = add_approved(an, db)
    same = an.put(f"{URL}/{product['id']}", json=body(db)).json()
    assert same["status"] == "approved" and same["checked_at"] == product["checked_at"]


@pytest.mark.parametrize(
    "change",
    [
        {"name": "Tên khác"},
        {"url": "https://s.shopee.vn/khac"},
        {"shop_name": "Shop khác"},
        {"shop_type": "preferred"},
        {"rating": 4.9},
        {"sold": 600},
        {"price": 90000},
        {"commission_rate": 5},
    ],
)
def test_changing_an_approved_product_needs_a_new_approval(an, db, change):
    product = add_approved(an, db)
    changed = an.put(f"{URL}/{product['id']}", json=body(db, **change)).json()
    assert changed["status"] == "draft" and changed["checked_at"] is None and changed["checked_by"] is None


def test_moving_an_approved_product_to_another_topic_needs_a_new_approval(an, db):
    product = add_approved(an, db)
    other = an.post("/api/knowledge/topics", json={"name": "Khác"}).json()["topics"][-1]
    moved = an.put(f"{URL}/{product['id']}", json=body(db, knowledge_topic_id=other["id"])).json()
    assert moved["status"] == "draft" and moved["topic"] == "Khác"


def test_unapprove_and_delete(an, db):
    product = add_approved(an, db)
    assert an.post(f"{URL}/{product['id']}/unapprove").json()["status"] == "draft"
    assert an.delete(f"{URL}/{product['id']}").json() == {"ok": True}
    assert an.get(URL).json() == []
    assert an.delete(f"{URL}/{product['id']}").status_code == 404


def csv_rows(an, query="") -> list[list[str]]:
    response = an.get(f"{URL}/export.csv{query}")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_csv_opens_in_excel_with_every_column(an, db, me):
    approved = add_approved(an, db, price=500000)
    header, row = csv_rows(an)
    checked = datetime.fromisoformat(approved["checked_at"])
    assert dict(zip(header, row, strict=True)) == {
        "Nhóm chủ đề": "Sức khỏe",
        "Sản phẩm": "Vừng đen rang",
        "Shop": "Nhà Vừng",
        "Loại shop": "Shopee Mall",
        "Sao": "4.8",
        "Đã bán": "500",
        "Giá (đ)": "500000",
        "Hoa hồng (%)": "10.0",
        "Hoa hồng ước tính (đ)": "50000",
        "Link": approved["url"],
        "Trạng thái": "Đã duyệt",
        "Ngày kiểm tra": (checked + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M"),
        "Người duyệt": me.name,
    }


def test_csv_keeps_the_rank_and_filters_of_the_list(an, db):
    other = an.post("/api/knowledge/topics", json={"name": "Khác"}).json()["topics"][-1]
    add_approved(an, db, name="Đắt", price=500000)
    add_approved(an, db, name="Rẻ", price=20000)
    add(an, db, name="Nháp", price=90000)
    add(an, db, name="Trà", price=10000, knowledge_topic_id=other["id"])

    def names(query: str = "") -> list[str]:
        return [row[1] for row in csv_rows(an, query)[1:]]

    assert names() == ["Đắt", "Nháp", "Rẻ", "Trà"]
    assert names("?status=approved") == ["Đắt", "Rẻ"]
    assert names(f"?topic_id={other['id']}") == ["Trà"]
    assert names("?q=rẻ") == ["Rẻ"]


@pytest.mark.parametrize("start", ["=", "+", "-", "@"])
def test_csv_cells_cannot_become_spreadsheet_formulas(an, db, start):
    add(an, db, name=f"{start}cmd", shop_name=f"{start}shop")
    row = csv_rows(an)[1]
    assert row[1] == f"'{start}cmd" and row[2] == f"'{start}shop"


def test_a_topic_with_products_cannot_be_deleted(an, db):
    topic = an.post("/api/knowledge/topics", json={"name": "Khác"}).json()["topics"][-1]
    product = add(an, db, knowledge_topic_id=topic["id"])
    refused = an.delete(f"/api/knowledge/topics/{topic['id']}")
    assert refused.status_code == 409 and "sản phẩm affiliate" in refused.json()["message"]
    an.delete(f"{URL}/{product['id']}")
    assert an.delete(f"/api/knowledge/topics/{topic['id']}").status_code == 200


def test_only_published_reels_are_listed_newest_first(an, db, me, storage):
    now = datetime.now(UTC)
    older = posted_video(db, storage, me, published_at=now - timedelta(days=2))
    newer = posted_video(db, storage, me, published_at=now - timedelta(days=1))
    went_live = posted_video(
        db, storage, me, status="scheduled", scheduled_at=now - timedelta(hours=1), published_at=now - timedelta(days=9)
    )
    posted_video(db, storage, me, status="scheduled", scheduled_at=now + timedelta(hours=1))
    posted_video(db, storage, me, status="pending")
    make_video(db, storage, me)

    rows = an.get(f"{URL}/videos").json()
    assert [row["id"] for row in rows] == [went_live.id, newer.id, older.id]
    assert rows[0]["reel_url"] and rows[0]["suggestions"] == ["sữa"] and rows[0]["pinned_comment"] == "ghim"
    # Its scheduled time, not the earlier end of the upload.
    assert datetime.fromisoformat(rows[0]["published_at"]) == now - timedelta(hours=1)


def test_attach_and_remove_products_on_a_posted_reel(an, db, me, storage):
    video = posted_video(db, storage, me)
    first, second = add_approved(an, db, name="Một"), add_approved(an, db, name="Hai")
    saved = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [first["id"], second["id"], first["id"]]}).json()
    assert [product["name"] for product in saved["products"]] == ["Một", "Hai"]
    kept = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [second["id"]]}).json()
    assert [product["id"] for product in kept["products"]] == [second["id"]]
    assert an.get(f"{URL}/videos").json()[0]["products"] == kept["products"]

    an.delete(f"{URL}/{second['id']}")
    assert an.get(f"{URL}/videos").json()[0]["products"] == []


def test_a_video_with_products_can_still_be_deleted(an, db, me, storage):
    video = posted_video(db, storage, me)
    product = add_approved(an, db)
    an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"]]})
    assert an.delete(f"/api/videos/{video.id}").status_code == 200
    assert an.get(f"{URL}/videos").json() == []
    assert [row["id"] for row in an.get(URL).json()] == [product["id"]]


def test_the_last_product_can_be_removed(an, db, me, storage):
    video = posted_video(db, storage, me)
    product = add_approved(an, db)
    an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"]]})
    assert an.put(f"{URL}/videos/{video.id}", json={"product_ids": []}).json()["products"] == []
    assert an.get(f"{URL}/videos").json()[0]["products"] == []


def test_each_reel_keeps_its_own_products(an, db, me, storage):
    first, second = posted_video(db, storage, me), posted_video(db, storage, me)
    one, two = add_approved(an, db, name="Một"), add_approved(an, db, name="Hai")
    an.put(f"{URL}/videos/{first.id}", json={"product_ids": [one["id"]]})
    saved = an.put(f"{URL}/videos/{second.id}", json={"product_ids": [two["id"]]}).json()
    assert [product["id"] for product in saved["products"]] == [two["id"]]
    an.put(f"{URL}/videos/{second.id}", json={"product_ids": []})
    by_video = {row["id"]: [product["id"] for product in row["products"]] for row in an.get(f"{URL}/videos").json()}
    assert by_video == {first.id: [one["id"]], second.id: []}


def test_only_approved_products_can_be_attached(an, db, me, storage):
    video = posted_video(db, storage, me)
    draft = add(an, db)
    refused = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [draft["id"]]})
    assert refused.status_code == 409 and an.get(f"{URL}/videos").json()[0]["products"] == []
    assert an.put(f"{URL}/videos/{video.id}", json={"product_ids": [999999]}).status_code == 404


def test_a_refused_save_keeps_what_was_attached(an, db, me, storage):
    # The page sends the whole selection, so a new draft arrives beside the products already there.
    video = posted_video(db, storage, me)
    product, draft = add_approved(an, db), add(an, db, name="Nháp")
    an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"]]})
    refused = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"], draft["id"]]})
    assert refused.status_code == 409
    assert [row["id"] for row in an.get(f"{URL}/videos").json()[0]["products"]] == [product["id"]]


def test_losing_approval_on_one_reel_does_not_open_another(an, db, me, storage):
    first, second = posted_video(db, storage, me), posted_video(db, storage, me)
    product = add_approved(an, db)
    an.put(f"{URL}/videos/{first.id}", json={"product_ids": [product["id"]]})
    an.post(f"{URL}/{product['id']}/unapprove")
    assert an.put(f"{URL}/videos/{second.id}", json={"product_ids": [product["id"]]}).status_code == 409


def test_a_product_that_lost_its_approval_stays_attached_and_shows_it(an, db, me, storage):
    video = posted_video(db, storage, me)
    product, other = add_approved(an, db), add_approved(an, db, name="Khác")
    an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"]]})
    an.post(f"{URL}/{product['id']}/unapprove")
    saved = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"], other["id"]]})
    assert saved.status_code == 200
    assert {row["status"] for row in saved.json()["products"]} == {"draft", "approved"}


def test_an_approved_product_with_a_new_banned_word_is_flagged_and_not_attachable(an, db, me, storage):
    video = posted_video(db, storage, me)
    attached, spare = add_approved(an, db, name="Trà thải độc"), add_approved(an, db, name="Trà thải độc gan")
    an.put(f"{URL}/videos/{video.id}", json={"product_ids": [attached["id"]]})
    first_topic(db).banned_words = ["thải độc"]
    db.commit()

    assert all("thải độc" in row["problems"][0] for row in an.get(URL).json())
    assert an.get(f"{URL}/videos").json()[0]["products"][0]["problems"]
    refused = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [attached["id"], spare["id"]]})
    assert refused.status_code == 409
    assert an.put(f"{URL}/videos/{video.id}", json={"product_ids": [attached["id"]]}).status_code == 200


@pytest.mark.parametrize("post", [None, {"status": "pending"}, {"status": "scheduled", "ahead": 1}])
def test_a_video_not_live_yet_takes_products_for_its_first_comment(an, db, me, storage, post):
    if post is None:
        video = make_video(db, storage, me)
    else:
        ahead = post.get("ahead")
        video = posted_video(
            db,
            storage,
            me,
            status=post["status"],
            scheduled_at=datetime.now(UTC) + timedelta(hours=ahead) if ahead else None,
        )
    product = add_approved(an, db)
    response = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"]]})
    # Products are chosen before posting now, so the first comment under the reel already holds their links;
    # the video is listed under "Video đã đăng" only once it is live.
    assert response.status_code == 200 and response.json() == {"id": video.id, "product_ids": [product["id"]]}
    assert an.get(f"{URL}/videos").json() == []
    assert an.get(f"/api/videos/{video.id}").json()["affiliate_product_ids"] == [product["id"]]


def test_a_scheduled_reel_takes_products_once_its_time_has_passed(an, db, me, storage):
    video = posted_video(db, storage, me, status="scheduled", scheduled_at=datetime.now(UTC) - timedelta(minutes=1))
    product = add_approved(an, db)
    assert an.put(f"{URL}/videos/{video.id}", json={"product_ids": [product["id"]]}).status_code == 200


def test_affiliate_needs_a_login(app, an, db, me, storage):
    video = posted_video(db, storage, me)
    product = add(an, db)
    anonymous = client_for(app)
    for response in (
        anonymous.get(URL),
        anonymous.get(f"{URL}/options"),
        anonymous.get(f"{URL}/export.csv"),
        anonymous.get(f"{URL}/videos"),
        anonymous.put(f"{URL}/videos/{video.id}", json={"product_ids": []}),
        anonymous.post(URL, json=body(db)),
        anonymous.put(f"{URL}/{product['id']}", json=body(db)),
        anonymous.post(f"{URL}/{product['id']}/approve"),
        anonymous.post(f"{URL}/{product['id']}/unapprove"),
        anonymous.delete(f"{URL}/{product['id']}"),
    ):
        assert response.status_code == 401, response.request.url
    assert an.get(URL).json()[0]["status"] == "draft"
