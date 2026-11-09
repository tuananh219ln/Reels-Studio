"""Adding Shopee products by their link or by Shopee Affiliate's "Lấy link hàng loạt" file: the worker reads the rest."""

import pytest
from conftest import client_for, first_topic, login, make_user, make_video
from fake_services import SHOPEE_APP_ID, SHOPEE_SECRET, shopee_offer
from sqlalchemy import select

from reels_api import affiliate_rounds, shopee
from reels_api.models import AffiliateProduct
from reels_api.sessions import now

PRODUCTS = "/api/affiliate-products"
SHORT = "https://s.shopee.vn/4LKghKN3cR"
REDIRECT = (
    "https://shopee.vn/opaanlp/1346703635/45113237093?__mobile__=1&utm_medium=affiliates&utm_source=an_17309060566"
)
FILE_HEADER = "Mã sản phẩm,Tên sản phẩm,Giá,Doanh thu,Tên cửa hàng,Tỉ lệ hoa hồng,Hoa hồng,Link sản phẩm,Link ưu đãi\n"
FILE_ROW = (
    '45113237093,"Combo 3 Gói Hạt Giống Rau Ăn Lá (Rau Muống,  Mồng Tơi)","45,0k",0,HỒNG HÀ F1 SEEDS,"2,5%",₫900,'
    "https://shopee.vn/product/1346703635/45113237093,https://s.shopee.vn/4LKghKN3cR\n"
)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def with_shopee_account(an) -> None:
    response = an.post(
        "/api/affiliate-accounts",
        json={"platform": "shopee", "name": "Shopee của An", "app_id": SHOPEE_APP_ID, "secret": SHOPEE_SECRET},
    )
    assert response.status_code == 201, response.text


def paste(an, db, *links: str):
    return an.post(f"{PRODUCTS}/links", json={"knowledge_topic_id": first_topic(db).id, "links": list(links)})


def import_file(an, db, text: str):
    return an.post(f"{PRODUCTS}/import", json={"knowledge_topic_id": first_topic(db).id, "text": text})


def run_lookups(db) -> None:
    for row in db.scalars(select(AffiliateProduct).where(AffiliateProduct.lookup_requested_at.is_not(None))).all():
        affiliate_rounds.lookup(db, row)


def only_product(an) -> dict:
    rows = an.get(PRODUCTS).json()
    assert len(rows) == 1
    return rows[0]


# Reading a link


@pytest.mark.parametrize(
    "url, item_id",
    [
        ("https://shopee.vn/product/1346703635/45113237093", 45113237093),
        ("https://shopee.vn/Hat-giong-rau-muong-i.1346703635.45113237093?sp_atk=x", 45113237093),
        (REDIRECT, 45113237093),
        ("https://shopee.vn/search?keyword=rau", None),
        (SHORT, None),
        ("https://example.com/product/1/2", None),
    ],
)
def test_the_item_id_is_read_from_a_product_link(url, item_id):
    assert shopee.item_id_of(url) == item_id


def test_a_short_link_is_followed_only_to_its_redirect(fakes):
    fakes.shopee_short_links["4LKghKN3cR"] = REDIRECT
    assert shopee.item_id_of(shopee.resolve(SHORT)) == 45113237093
    with pytest.raises(shopee.ShopeeError):
        shopee.resolve("https://s.shopee.vn/missing")


# Pasting links


def test_a_pasted_short_link_is_filled_by_the_worker_with_the_members_own_link_kept(an, db, fakes):
    with_shopee_account(an)
    fakes.shopee_short_links["4LKghKN3cR"] = REDIRECT
    fakes.shopee_items[45113237093] = shopee_offer(45113237093, "Hạt giống rau muống", sales=2500)
    response = paste(an, db, f"  {SHORT}  ")
    assert response.status_code == 201, response.text
    assert response.json() == {"added": 1, "skipped": []}
    waiting = only_product(an)
    assert waiting["lookup"] == "pending"
    assert an.post(f"{PRODUCTS}/{waiting['id']}/approve").status_code == 409
    run_lookups(db)
    product = only_product(an)
    assert product["lookup"] is None and product["name"] == "Hạt giống rau muống"
    assert (product["sold"], product["rating"], product["shop_type"]) == (2500, 4.9, "mall")
    assert (product["price"], product["commission_rate"]) == (250000, 8)
    assert product["url"] == SHORT and product["from_shopee_api"]
    assert product["page_url"] == "https://shopee.vn/product/1/45113237093"
    assert an.post(f"{PRODUCTS}/{product['id']}/approve").status_code == 200


def test_pasting_needs_a_shopee_account_with_app_id_in_the_team(an, db):
    response = paste(an, db, SHORT)
    assert response.status_code == 422 and "App ID" in response.json()["message"]
    assert an.get(PRODUCTS).json() == []


def test_another_members_account_reads_the_teams_products(app, an, db, fakes):
    with_shopee_account(an)
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    binh = client_for(app)
    login(binh, "binh@doi.vn")
    fakes.shopee_items[42] = shopee_offer(42, "Nồi hầm")
    assert paste(binh, db, "https://shopee.vn/product/1/42").status_code == 201
    run_lookups(db)
    assert only_product(binh)["name"] == "Nồi hầm"


@pytest.mark.parametrize("link", ["https://lazada.vn/products/abc", "shopee.vn/product/1/2", "javascript:alert(1)"])
def test_only_shopee_links_are_taken(an, db, link):
    with_shopee_account(an)
    assert paste(an, db, link).status_code == 422


def test_a_link_already_in_the_list_is_skipped(an, db, fakes):
    with_shopee_account(an)
    fakes.shopee_items[42] = shopee_offer(42, "Nồi hầm")
    paste(an, db, "https://shopee.vn/product/1/42", SHORT)
    response = paste(an, db, "https://shopee.vn/Noi-ham-i.1.42", SHORT, "https://shopee.vn/product/1/42")
    assert response.json()["added"] == 0 and len(response.json()["skipped"]) == 3
    assert len(an.get(PRODUCTS).json()) == 2


def test_a_short_link_to_a_product_already_listed_says_so(an, db, fakes):
    with_shopee_account(an)
    fakes.shopee_items[45113237093] = shopee_offer(45113237093, "Hạt giống rau muống")
    fakes.shopee_short_links["4LKghKN3cR"] = REDIRECT
    paste(an, db, "https://shopee.vn/product/1346703635/45113237093")
    run_lookups(db)
    paste(an, db, SHORT)
    run_lookups(db)
    failed = next(row for row in an.get(PRODUCTS).json() if row["lookup"] == "failed")
    assert "đã có trong danh sách" in failed["lookup_error"]


def test_a_failed_lookup_is_shown_kept_and_can_be_asked_again(an, db, fakes):
    with_shopee_account(an)
    paste(an, db, SHORT)  # the fake has no redirect for it yet
    run_lookups(db)
    product = only_product(an)
    assert product["lookup"] == "failed" and product["lookup_error"]
    run_lookups(db)  # nothing is retried by itself
    fakes.shopee_short_links["4LKghKN3cR"] = REDIRECT
    fakes.shopee_items[45113237093] = shopee_offer(45113237093, "Hạt giống rau muống")
    assert an.post(f"{PRODUCTS}/{product['id']}/lookup").json()["lookup"] == "pending"
    run_lookups(db)
    assert only_product(an)["name"] == "Hạt giống rau muống"


def test_a_product_without_an_affiliate_offer_says_so(an, db, fakes):
    with_shopee_account(an)
    fakes.shopee_items[42] = None
    paste(an, db, "https://shopee.vn/product/1/42")
    run_lookups(db)
    assert "không có hoa hồng" in only_product(an)["lookup_error"]


# Pasting links on a video ("Dán link aff")


def paste_on(an, video, *links: str):
    return an.post(f"{PRODUCTS}/videos/{video.id}/links", json={"links": list(links)})


def test_without_an_app_id_a_link_pasted_on_a_video_is_a_draft_holding_only_the_link(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    response = paste_on(an, video, f"  {SHORT}  ")
    assert response.status_code == 200, response.text
    pasted = next(group for group in response.json()["keywords"] if group["pasted"])
    (row,) = pasted["products"]
    assert (row["url"], row["status"], row["lookup"]) == (SHORT, "draft", None)
    assert row["knowledge_topic_id"] == first_topic(db).id
    assert row["problems"], "the rest is filled in by hand before it can be chosen"
    chosen = an.post(f"{PRODUCTS}/videos/{video.id}/choose", json={"product_id": row["id"]})
    assert chosen.status_code == 409


def test_with_an_app_id_a_link_pasted_on_a_video_is_read_by_the_worker_and_can_be_chosen(an, db, me, storage, fakes):
    with_shopee_account(an)
    video = make_video(db, storage, me, scene_count=1)
    fakes.shopee_short_links["4LKghKN3cR"] = REDIRECT
    fakes.shopee_items[45113237093] = shopee_offer(45113237093, "Hạt giống rau muống", sales=2500)
    (row,) = next(group for group in paste_on(an, video, SHORT).json()["keywords"] if group["pasted"])["products"]
    assert row["lookup"] == "pending"
    run_lookups(db)
    chosen = an.post(f"{PRODUCTS}/videos/{video.id}/choose", json={"product_id": row["id"]}).json()
    assert chosen["attached_ids"] == [row["id"]]


def test_a_link_already_listed_is_reused_and_pasting_twice_lists_it_once(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    import_file(an, db, FILE_HEADER + FILE_ROW)
    paste_on(an, video, SHORT)
    groups = paste_on(an, video, SHORT, "https://shopee.vn/product/1346703635/45113237093").json()["keywords"]
    (pasted,) = [group for group in groups if group["pasted"]]
    assert [row["name"] for row in pasted["products"]] == ["Combo 3 Gói Hạt Giống Rau Ăn Lá (Rau Muống, Mồng Tơi)"]
    assert len(an.get(PRODUCTS).json()) == 1


def test_a_new_search_keeps_the_pasted_links(an, db, me, storage, fakes):
    with_shopee_account(an)
    video = make_video(db, storage, me, scene_count=1)
    paste_on(an, video, "https://shopee.vn/product/1/42")
    video.suggest_requested_at, video.suggest_by_id = now(), me.id
    db.commit()
    affiliate_rounds.suggest(db, video)
    groups = an.get(f"{PRODUCTS}/videos/{video.id}/suggestions").json()["keywords"]
    assert [group["keyword"] for group in groups if group["pasted"]] == [affiliate_rounds.PASTED]
    assert any(not group["pasted"] for group in groups)


@pytest.mark.parametrize("link", ["https://lazada.vn/products/abc", "javascript:alert(1)"])
def test_only_shopee_links_are_pasted_on_a_video(an, db, me, storage, link):
    video = make_video(db, storage, me, scene_count=1)
    assert paste_on(an, video, link).status_code == 422
    assert an.get(PRODUCTS).json() == []


# Importing Shopee Affiliate's file


def test_the_file_from_shopee_affiliate_is_imported_as_drafts(an, db):
    response = import_file(an, db, f"﻿{FILE_HEADER}{FILE_ROW}\n")
    assert response.status_code == 201, response.text
    assert response.json() == {"added": 1, "updated": 0, "kept": 0, "others": [], "errors": [], "lookup": False}
    product = only_product(an)
    assert product["name"] == "Combo 3 Gói Hạt Giống Rau Ăn Lá (Rau Muống, Mồng Tơi)"
    assert (product["price"], product["commission_rate"], product["shop_name"]) == (45000, 2.5, "HỒNG HÀ F1 SEEDS")
    assert product["url"] == SHORT and product["page_url"] == "https://shopee.vn/product/1346703635/45113237093"
    assert product["status"] == "draft" and product["lookup"] is None
    # Stars, sales and the shop's type are not in the file: a member fills them in before approving.
    assert product["problems"]


def test_an_imported_product_is_completed_by_the_worker_when_the_team_has_a_shopee_account(an, db, fakes):
    with_shopee_account(an)
    fakes.shopee_items[45113237093] = shopee_offer(45113237093, "Hạt giống rau muống", commissionRate="0.025")
    assert import_file(an, db, FILE_HEADER + FILE_ROW).json()["lookup"] is True
    run_lookups(db)
    product = only_product(an)
    assert (product["rating"], product["sold"], product["shop_type"]) == (4.9, 1500, "mall")
    assert product["url"] == SHORT and not product["problems"]


def test_importing_again_updates_the_product_instead_of_adding_it_twice(an, db):
    import_file(an, db, FILE_HEADER + FILE_ROW)
    again = FILE_ROW.replace('"45,0k"', '"1,2tr"').replace('"2,5%"', "3%")
    assert import_file(an, db, FILE_HEADER + again).json()["updated"] == 1
    product = only_product(an)
    assert (product["price"], product["commission_rate"]) == (1_200_000, 3)


def test_bad_rows_are_listed_and_the_good_ones_imported(an, db):
    bad = "abc,Tên,10k,0,Shop,1%,₫1,https://shopee.vn/product/1/1,\n" + "7,Tên 2,không rõ,0,Shop,1%,₫1,,\n"
    response = import_file(an, db, FILE_HEADER + FILE_ROW + bad)
    assert response.json()["added"] == 1
    assert [error["row"] for error in response.json()["errors"]] == [3, 4]


def test_a_file_from_elsewhere_is_refused_with_the_missing_columns(an, db):
    response = import_file(an, db, "Tên,Giá\nA,1\n")
    assert response.status_code == 422 and "mã sản phẩm" in response.json()["message"]


def test_a_semicolon_file_saved_by_excel_is_read(an, db):
    text = (FILE_HEADER + FILE_ROW).replace(",", ";").replace('"45;0k"', '"45,0k"').replace('"2;5%"', '"2,5%"')
    text = text.replace("Rau Muống;  Mồng Tơi", "Rau Muống,  Mồng Tơi")
    assert import_file(an, db, text).json()["added"] == 1


def test_editing_by_hand_clears_a_failed_lookup(an, db, fakes):
    with_shopee_account(an)
    paste(an, db, SHORT)
    run_lookups(db)
    product = only_product(an)
    body = {
        "knowledge_topic_id": product["knowledge_topic_id"],
        "name": "Hạt giống",
        "url": SHORT,
        "shop_name": "Shop",
        "shop_type": "mall",
        "rating": 4.8,
        "sold": 200,
        "price": 45000,
        "commission_rate": 2.5,
    }
    assert an.put(f"{PRODUCTS}/{product['id']}", json=body).json()["lookup"] is None
