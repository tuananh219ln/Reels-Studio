"""Issue #47: each member's own affiliate accounts, Page owners, the Page's Shopee links in comments, Shopee's
suggestions, the daily check, orders, and TikTok versions posted by hand."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import client_for, first_topic, login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, SHOPEE_APP_ID, SHOPEE_SECRET, shopee_offer
from sqlalchemy import select

from reels_api import affiliate_rounds, fanpages, post_comments
from reels_api.models import (
    AffiliateAccount,
    AffiliateConversion,
    AffiliateLink,
    AffiliateProduct,
    Fanpage,
    Publication,
    Video,
    VideoAffiliateProduct,
)

ACCOUNTS = "/api/affiliate-accounts"
PRODUCTS = "/api/affiliate-products"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def binh(app, other):
    client = client_for(app)
    login(client, "binh@doi.vn")
    return client


def shopee_account(an, secret=SHOPEE_SECRET, name="Shopee của An") -> dict:
    response = an.post(ACCOUNTS, json={"platform": "shopee", "name": name, "app_id": SHOPEE_APP_ID, "secret": secret})
    assert response.status_code == 201, response.text
    return response.json()


def tiktok_account(an, name="TikTok của An") -> dict:
    response = an.post(
        ACCOUNTS, json={"platform": "tiktok", "name": name, "profile_url": "https://www.tiktok.com/@an.duongsinh"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def page_of(db, owner) -> Fanpage:
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, owner.id)
    db.commit()
    return page


def live_post(db, storage, user, fakes, page: Fanpage) -> Publication:
    video = make_video(db, storage, user, scene_count=1)
    video.pinned_comment = "Ghim nhé"
    fakes.reels[f"reel-{video.id}"] = {"uploaded": True, "state": "published"}
    post = Publication(
        video_id=video.id,
        platform="facebook",
        created_by_id=user.id,
        fanpage_id=page.id,
        remote_id=f"reel-{video.id}",
        status="published",
        published_at=datetime.now(UTC) - timedelta(minutes=10),
        auto_comment=True,
    )
    db.add(post)
    db.commit()
    return post


def product(db, user, name="Nồi hầm", status="approved", **fields) -> AffiliateProduct:
    defaults = {"shop_name": "Shop", "shop_type": "mall", "rating": 4.9, "sold": 1000, "price": 200000}
    row = AffiliateProduct(
        knowledge_topic_id=first_topic(db).id,
        name=name,
        commission_rate=8,
        status=status,
        created_by_id=user.id,
        **(defaults | fields),
    )
    db.add(row)
    db.commit()
    return row


def attach(db, video_id: int, row: AffiliateProduct) -> None:
    db.add(VideoAffiliateProduct(video_id=video_id, product_id=row.id))
    db.commit()


# Accounts belong to one member


def test_a_secret_goes_in_and_never_comes_back(an):
    account = shopee_account(an)
    assert SHOPEE_SECRET not in str(account) and account["secret_tail"] == SHOPEE_SECRET[-4:]
    assert SHOPEE_SECRET not in an.get(ACCOUNTS).text


def test_editing_without_a_secret_keeps_the_saved_one(an, db):
    account = shopee_account(an)
    response = an.put(
        f"{ACCOUNTS}/{account['id']}",
        json={"platform": "shopee", "name": "Đổi tên", "app_id": SHOPEE_APP_ID, "secret": ""},
    )
    assert response.status_code == 200 and response.json()["secret_tail"] == SHOPEE_SECRET[-4:]


def test_another_member_neither_sees_nor_changes_my_accounts(an, binh):
    account = shopee_account(an)
    assert binh.get(ACCOUNTS).json() == []
    assert binh.put(f"{ACCOUNTS}/{account['id']}", json={"platform": "shopee", "name": "x"}).status_code == 404
    assert binh.delete(f"{ACCOUNTS}/{account['id']}").status_code == 404
    assert binh.post(f"{ACCOUNTS}/{account['id']}/check").status_code == 404


def test_a_tiktok_account_needs_its_profile_link(an):
    response = an.post(ACCOUNTS, json={"platform": "tiktok", "name": "TikTok", "profile_url": "https://evil.vn/@a"})
    assert response.status_code == 422 and "tiktok.com/@" in response.json()["message"]
    assert tiktok_account(an)["profile_url"] == "https://www.tiktok.com/@an.duongsinh"


def test_checking_an_account_says_whether_shopee_takes_its_keys(an, fakes):
    good = shopee_account(an)
    bad = shopee_account(an, secret="sai-secret", name="Sai")
    assert an.post(f"{ACCOUNTS}/{good['id']}/check").json() == {"ok": True, "error": None}
    assert "App ID/Secret" in an.post(f"{ACCOUNTS}/{bad['id']}/check").json()["error"]


# Page owners


def test_the_member_who_connects_a_page_owns_it_and_a_new_token_keeps_the_owner(db, me, other):
    page = page_of(db, me)
    fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, other.id)
    assert page.owner_id == me.id


def test_only_the_owner_hands_a_page_over_and_its_shopee_account_goes_with_the_old_owner(an, binh, db, me, other):
    page = page_of(db, me)
    account = shopee_account(an)
    assert an.put(f"/api/fanpages/{page.id}/shopee-account", json={"account_id": account["id"]}).status_code == 200
    assert binh.put(f"/api/fanpages/{page.id}/owner", json={"user_id": other.id}).status_code == 403
    assert binh.put(f"/api/fanpages/{page.id}/shopee-account", json={"account_id": None}).status_code == 403
    (row,) = binh.get("/api/fanpages").json()
    assert row["owner"]["name"] == me.name and row["shopee_account"] is None, "the owner's account stays private"

    assert an.put(f"/api/fanpages/{page.id}/owner", json={"user_id": other.id}).status_code == 200
    db.expire_all()
    assert (page.owner_id, page.shopee_account_id) == (other.id, None)


def test_a_page_takes_only_its_owners_own_shopee_account(an, binh, db, me):
    page = page_of(db, me)
    theirs = binh.post(
        ACCOUNTS, json={"platform": "shopee", "name": "B", "app_id": SHOPEE_APP_ID, "secret": "x"}
    ).json()
    assert an.put(f"/api/fanpages/{page.id}/shopee-account", json={"account_id": theirs["id"]}).status_code == 422


def test_a_page_nobody_owns_is_claimed_only_for_oneself(an, db, me, other):
    page = page_of(db, me)
    page.owner_id = None
    db.commit()
    assert an.put(f"/api/fanpages/{page.id}/owner", json={"user_id": other.id}).status_code == 422
    assert an.put(f"/api/fanpages/{page.id}/owner", json={"user_id": me.id}).json()[0]["mine"] is True


# Links in the comment


def test_a_page_with_a_shopee_account_gets_its_own_link_once_naming_the_video_and_page(an, db, me, storage, fakes):
    page = page_of(db, me)
    page.shopee_account_id = shopee_account(an)["id"]
    post = live_post(db, storage, me, fakes, page)
    row = product(db, me, url="https://s.shopee.vn/link-cua-nguoi-khac", page_url="https://shopee.vn/product/1/9")
    attach(db, post.video_id, row)

    post_comments.write(db, post)
    (made,) = fakes.shopee_links
    assert made["origin"] == "https://shopee.vn/product/1/9"
    assert made["sub_ids"] == [f"v{post.video_id}", f"p{page.id}"]
    assert post.comment_text == f"Ghim nhé\nNồi hầm: {made['link']}"

    post.comment_requested_at = datetime.now(UTC)
    db.commit()
    post_comments.write(db, post)
    assert len(fakes.shopee_links) == 1, "the link is kept, not made again"
    assert db.scalar(select(AffiliateLink.url)) == made["link"]


def test_a_page_without_an_account_keeps_the_pasted_link_and_skips_api_products(db, me, storage, fakes):
    page = page_of(db, me)
    post = live_post(db, storage, me, fakes, page)
    attach(db, post.video_id, product(db, me, "Nồi hầm", url="https://s.shopee.vn/dan-tay"))
    attach(db, post.video_id, product(db, me, "Hạt chia", page_url="https://shopee.vn/product/1/2", shopee_item_id=2))
    post_comments.write(db, post)
    assert post.comment_text == "Ghim nhé\nNồi hầm: https://s.shopee.vn/dan-tay"
    assert fakes.shopee_links == []


def test_tiktok_shop_products_never_go_in_a_facebook_comment(db, me, storage, fakes):
    page = page_of(db, me)
    post = live_post(db, storage, me, fakes, page)
    db.add(VideoAffiliateProduct(video_id=post.video_id, product_id=product(db, me, url="https://x.vn/a").id))
    tiktok = product(db, me, "Trà gừng", platform="tiktok_shop", url="https://www.tiktok.com/view/product/1")
    attach(db, post.video_id, tiktok)
    post_comments.write(db, post)
    assert "Trà gừng" not in post.comment_text


def test_a_shopee_failure_is_recorded_and_writes_nothing(an, db, me, storage, fakes):
    page = page_of(db, me)
    page.shopee_account_id = shopee_account(an)["id"]
    post = live_post(db, storage, me, fakes, page)
    attach(db, post.video_id, product(db, me, page_url="https://shopee.vn/product/1/9"))
    fakes.shopee_mode = "rate_limit"
    post_comments.write(db, post)
    assert post.comment_error.startswith("Không tạo được link Shopee: Shopee đang giới hạn")
    assert fakes.facebook_comments == {}
    assert post_comments.due_posts(db) == [], "it waits for a member, never loops"


# Suggestions


def test_asking_for_suggestions_needs_my_own_shopee_account(an, binh, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    response = binh.post(f"{PRODUCTS}/videos/{video.id}/suggestions")
    assert response.status_code == 422 and "Tài khoản affiliate" in response.json()["message"]
    shopee_account(an)
    assert an.post(f"{PRODUCTS}/videos/{video.id}/suggestions").json()["state"] == "pending"


def test_the_worker_keeps_the_products_meeting_the_rules_best_first(an, db, me, storage, fakes):
    shopee_account(an)
    video = make_video(db, storage, me, scene_count=1)
    video.affiliates = ["Vừng đen"]
    db.commit()
    an.post(f"{PRODUCTS}/videos/{video.id}/suggestions")
    db.expire_all()
    affiliate_rounds.suggest(db, db.get(Video, video.id))

    (group,) = an.get(f"{PRODUCTS}/videos/{video.id}/suggestions").json()["keywords"]
    assert group["keyword"] == "Vừng đen"
    names = [row["name"] for row in group["products"]]
    assert names == ["Vừng đen loại 1", "Vừng đen loại 2"], "the 4.2-star one is left out, the richer first"
    first = group["products"][0]
    assert (first["status"], first["from_shopee_api"], first["commission_rate"], first["price"]) == (
        "draft",
        True,
        8.0,
        250000,
    )
    assert all("productOfferV2" in query and "Vừng đen" in query for query in fakes.shopee_queries)


def test_searching_twice_does_not_add_the_same_product_twice(an, db, me, storage, fakes):
    shopee_account(an)
    video = make_video(db, storage, me, scene_count=1)
    for _ in range(2):
        video.suggest_requested_at, video.suggest_by_id = datetime.now(UTC), me.id
        db.commit()
        affiliate_rounds.suggest(db, video)
    assert db.query(AffiliateProduct).count() == 2


def test_a_failed_search_is_shown_and_not_repeated(an, db, me, storage, fakes):
    shopee_account(an)
    video = make_video(db, storage, me, scene_count=1)
    video.suggest_requested_at, video.suggest_by_id = datetime.now(UTC), me.id
    db.commit()
    fakes.shopee_mode = "error500"
    affiliate_rounds.suggest(db, video)
    video = db.get(Video, video.id)
    assert video.suggest_requested_at is None and "HTTP 500" in video.suggest_error


def test_choosing_a_suggestion_approves_and_attaches_it(an, db, me, storage, fakes):
    video = make_video(db, storage, me, scene_count=1)
    row = product(db, me, status="draft", shopee_item_id=5, page_url="https://shopee.vn/product/1/5")
    result = an.post(f"{PRODUCTS}/videos/{video.id}/choose", json={"product_id": row.id}).json()
    assert result["attached_ids"] == [row.id]
    db.expire_all()
    assert db.get(AffiliateProduct, row.id).status == "approved"


def test_a_product_failing_the_rules_cannot_be_chosen(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    row = product(db, me, status="draft", rating=4.0)
    response = an.post(f"{PRODUCTS}/videos/{video.id}/choose", json={"product_id": row.id})
    assert response.status_code == 409 and "4.7" in response.json()["message"]


def test_a_new_script_asks_for_suggestions_when_its_writer_has_an_account(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    affiliate_rounds.ask_after_script(db, video, me.id)
    assert video.suggest_requested_at is None
    shopee_account(an)
    affiliate_rounds.ask_after_script(db, video, me.id)
    assert video.suggest_requested_at is not None and video.suggest_by_id == me.id


# The daily check


def test_a_product_shopee_no_longer_offers_goes_back_to_draft(an, db, me, fakes):
    shopee_account(an)
    row = product(db, me, shopee_item_id=77)
    fakes.shopee_items[77] = None
    affiliate_rounds.check_offer(db, row)
    assert row.status == "draft" and row.offer_checked_at is not None


def test_an_expired_commission_sends_a_product_back_to_draft(an, db, me, fakes):
    shopee_account(an)
    row = product(db, me, shopee_item_id=78)
    past = int((datetime.now(UTC) - timedelta(days=1)).timestamp())
    fakes.shopee_items[78] = shopee_offer(78, "Nồi hầm", periodEndTime=past)
    affiliate_rounds.check_offer(db, row)
    assert row.status == "draft"


def test_a_product_still_offered_keeps_its_approval_with_new_figures(an, db, me, fakes):
    shopee_account(an)
    row = product(db, me, shopee_item_id=79)
    fakes.shopee_items[79] = shopee_offer(79, "Nồi hầm", sales=5000)
    affiliate_rounds.check_offer(db, row)
    assert (row.status, row.sold) == ("approved", 5000)


# Orders


def test_orders_are_kept_once_with_their_video_and_page_and_only_their_owner_sees_them(
    an, binh, db, me, storage, fakes
):
    account = db.get(AffiliateAccount, shopee_account(an)["id"])
    page = page_of(db, me)
    video = make_video(db, storage, me, scene_count=1)
    bought = int(datetime.now(UTC).timestamp()) - 3600
    fakes.shopee_conversions = [
        {
            "purchaseTime": bought,
            "conversionId": 1,
            "utmContent": f"v{video.id}-p{page.id}",
            "orders": [
                {
                    "orderId": "A1",
                    "orderStatus": "PENDING",
                    "items": [{"itemId": 9, "itemName": "Nồi hầm", "itemTotalCommission": "16000"}],
                }
            ],
        }
    ]
    affiliate_rounds.read_orders(db, account)
    affiliate_rounds.read_orders(db, account)
    (row,) = db.scalars(select(AffiliateConversion))
    assert (row.video_id, row.fanpage_id, row.commission, row.status) == (video.id, page.id, 16000, "PENDING")

    mine = an.get(f"{ACCOUNTS}/revenue").json()
    assert (mine["orders"], mine["commission"], mine["lines"][0]["fanpage"]) == (1, 16000, "Trang Dưỡng Sinh")
    assert binh.get(f"{ACCOUNTS}/revenue").json()["orders"] == 0


# TikTok, posted by hand


def test_the_tiktok_version_is_its_own_video_linked_to_the_facebook_one(an, db, me, storage, fakes):
    source = make_video(db, storage, me, scene_count=1)
    draft = an.post(
        f"/api/videos/{source.id}/clone", json={"request": "Viết lại cho TikTok", "platform": "tiktok"}
    ).json()
    assert (draft["platform"], draft["variant_of"]["id"]) == ("tiktok", source.id)
    assert [variant["id"] for variant in an.get(f"/api/videos/{source.id}").json()["variants"]] == [draft["id"]]


def test_a_tiktok_video_takes_only_tiktok_shop_products(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    video.platform = "tiktok"
    db.commit()
    shopee = product(db, me, url="https://s.shopee.vn/a")
    tiktok = product(db, me, "Trà gừng", platform="tiktok_shop", url="https://www.tiktok.com/view/product/1")
    response = an.put(f"{PRODUCTS}/videos/{video.id}", json={"product_ids": [shopee.id]})
    assert response.status_code == 409 and "TikTok Shop" in response.json()["message"]
    assert an.put(f"{PRODUCTS}/videos/{video.id}", json={"product_ids": [tiktok.id]}).status_code == 200


def test_a_hand_made_tiktok_post_is_recorded_on_my_own_account_only(an, binh, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    video.platform, video.mp4_key = "tiktok", "videos/x/video.mp4"
    db.commit()
    account = tiktok_account(an)
    url = "https://www.tiktok.com/@an.duongsinh/video/7300000000000000001"
    assert (
        binh.post(f"/api/tiktok/videos/{video.id}/posts", json={"account_id": account["id"], "url": url}).status_code
        == 422
    )
    bad = an.post(f"/api/tiktok/videos/{video.id}/posts", json={"account_id": account["id"], "url": "https://x.vn/1"})
    assert bad.status_code == 422

    saved = an.post(f"/api/tiktok/videos/{video.id}/posts", json={"account_id": account["id"], "url": url}).json()
    (post,) = saved["tiktok_posts"]
    assert (post["url"], post["account"]) == (url, "TikTok của An")
    assert saved["publications"] == [], "a TikTok post is not a Facebook one"
    assert an.get("/api/posts").json() == []
    row = db.get(Publication, post["id"])
    assert row.remote_id is None, "no Facebook reads touch it"

    assert binh.delete(f"/api/tiktok/posts/{post['id']}").status_code == 403
    assert an.delete(f"/api/tiktok/posts/{post['id']}").json()["tiktok_posts"] == []


def test_a_facebook_video_cannot_record_a_tiktok_post(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    video.mp4_key = "videos/x/video.mp4"
    db.commit()
    account = tiktok_account(an)
    response = an.post(
        f"/api/tiktok/videos/{video.id}/posts",
        json={"account_id": account["id"], "url": "https://www.tiktok.com/@a/video/1"},
    )
    assert response.status_code == 422
