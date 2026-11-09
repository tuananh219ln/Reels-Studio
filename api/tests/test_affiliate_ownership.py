"""The Affiliate screen by owner (docs/specs/affiliate-screen-ownership): whose posted videos are "mine", the Pages
each video went to, and whose Shopee account gets the commission of each product in its comment."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import client_for, first_topic, login, make_user, make_video
from fake_services import FACEBOOK_TOKEN, SHOPEE_APP_ID, SHOPEE_SECRET

from reels_api import affiliate, crypto, fanpages, post_comments
from reels_api.models import AffiliateAccount, AffiliateProduct, Fanpage, Publication, VideoAffiliateProduct

URL = "/api/affiliate-products"


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


def page(db, owner, page_id: str, name: str) -> Fanpage:
    row = fanpages.save(db, page_id, name, FACEBOOK_TOKEN, owner.id)
    db.commit()
    return row


def shopee_account(db, owner, app_id: str | None = SHOPEE_APP_ID) -> AffiliateAccount:
    row = AffiliateAccount(
        platform="shopee",
        owner_id=owner.id,
        name=f"Shopee của {owner.name}",
        app_id=app_id,
        secret_encrypted=crypto.encrypt(SHOPEE_SECRET) if app_id else None,
    )
    db.add(row)
    db.commit()
    return row


def post(db, video, by, fanpage=None, platform="facebook", account=None, minutes_ago=10) -> Publication:
    row = Publication(
        video_id=video.id,
        platform=platform,
        created_by_id=by.id,
        fanpage_id=fanpage.id if fanpage else None,
        affiliate_account_id=account.id if account else None,
        remote_id=f"reel-{video.id}-{minutes_ago}" if platform == "facebook" else None,
        post_url="https://www.tiktok.com/@a/video/1" if platform == "tiktok" else None,
        status="published",
        published_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(row)
    db.commit()
    return row


def product(db, user, name="Nồi hầm", **fields) -> AffiliateProduct:
    defaults = {"shop_name": "Shop", "shop_type": "mall", "rating": 4.9, "sold": 1000, "price": 200000}
    row = AffiliateProduct(
        knowledge_topic_id=first_topic(db).id,
        name=name,
        commission_rate=8,
        status="approved",
        created_by_id=user.id,
        **(defaults | fields),
    )
    db.add(row)
    db.commit()
    return row


def attach(db, video, row) -> None:
    db.add(VideoAffiliateProduct(video_id=video.id, product_id=row.id))
    db.commit()


def videos(client) -> dict[int, dict]:
    return {row["id"]: row for row in client.get(f"{URL}/videos").json()}


# Whose video


def test_a_video_is_mine_when_i_posted_it_or_it_is_on_my_page(an, db, me, other, storage):
    mine_page, their_page = page(db, me, "p-an", "Trang An"), page(db, other, "p-binh", "Trang Bình")
    on_my_page = make_video(db, storage, other, scene_count=1)
    post(db, on_my_page, other, mine_page)
    i_posted = make_video(db, storage, me, scene_count=1)
    post(db, i_posted, me, their_page)
    theirs = make_video(db, storage, other, scene_count=1)
    post(db, theirs, other, their_page)

    rows = videos(an)
    assert rows[on_my_page.id]["mine"] is True
    assert rows[i_posted.id]["mine"] is True
    assert rows[theirs.id]["mine"] is False


def test_a_video_stays_mine_when_a_teammate_posts_it_again_on_their_page(an, db, me, other, storage):
    mine_page, their_page = page(db, me, "p-an", "Trang An"), page(db, other, "p-binh", "Trang Bình")
    video = make_video(db, storage, me, scene_count=1)
    post(db, video, me, mine_page, minutes_ago=60)
    post(db, video, other, their_page, minutes_ago=5)

    row = videos(an)[video.id]
    assert row["mine"] is True
    assert [(one["fanpage_name"], one["owner_name"]) for one in row["posts"]] == [
        ("Trang Bình", "Trần Bình"),
        ("Trang An", "Nguyễn Văn An"),
    ]


def test_a_tiktok_post_belongs_to_the_owner_of_its_tiktok_account(an, binh, db, me, other, storage):
    account = AffiliateAccount(platform="tiktok", owner_id=other.id, name="@binh.khoe", profile_url="x")
    db.add(account)
    db.commit()
    video = make_video(db, storage, me, scene_count=1)
    post(db, video, me, platform="tiktok", account=account)

    (one,) = videos(binh)[video.id]["posts"]
    assert one == {
        "platform": "tiktok",
        "fanpage_id": None,
        "name": "@binh.khoe",
        "fanpage_name": None,
        "owner_id": other.id,
        "owner_name": "Trần Bình",
        "has_shopee_account": False,
        "comment": "off",
        "comment_error": None,
    }
    assert videos(binh)[video.id]["mine"] is True


def test_only_live_posts_are_listed(an, db, me, storage):
    mine_page = page(db, me, "p-an", "Trang An")
    video = make_video(db, storage, me, scene_count=1)
    post(db, video, me, mine_page)
    gone = post(db, video, me, page(db, me, "p-an-2", "Trang An 2"), minutes_ago=1)
    gone.status = "deleted"
    db.commit()
    assert [one["fanpage_name"] for one in videos(an)[video.id]["posts"]] == ["Trang An"]


# A Page's Shopee account counts only when its comments can use it


def test_a_page_has_a_shopee_account_only_when_its_owner_can_make_links_with_it(an, db, me, other, storage):
    with_keys, without_keys = page(db, me, "p-1", "Có App ID"), page(db, me, "p-2", "Thiếu App ID")
    not_the_owners = page(db, me, "p-3", "Tài khoản người khác")
    with_keys.shopee_account_id = shopee_account(db, me).id
    without_keys.shopee_account_id = shopee_account(db, me, app_id=None).id
    not_the_owners.shopee_account_id = shopee_account(db, other).id
    db.commit()
    video = make_video(db, storage, me, scene_count=1)
    for minutes, fanpage in enumerate((with_keys, without_keys, not_the_owners)):
        post(db, video, me, fanpage, minutes_ago=minutes + 1)

    flags = {one["fanpage_name"]: one["has_shopee_account"] for one in videos(an)[video.id]["posts"]}
    assert flags == {"Có App ID": True, "Thiếu App ID": False, "Tài khoản người khác": False}


# Whose commission


@pytest.mark.parametrize(
    ("has_account", "fields", "kind"),
    [
        (True, {"url": "https://s.shopee.vn/a", "page_url": "https://shopee.vn/product/1/2"}, "page_account"),
        (True, {"page_url": "https://shopee.vn/product/1/2"}, "page_account"),
        (False, {"url": "https://s.shopee.vn/a"}, "saved_link"),
        (False, {"page_url": "https://shopee.vn/product/1/2"}, "no_link"),
    ],
)
def test_commission_goes_where_the_comment_link_comes_from(db, me, storage, fakes, has_account, fields, kind):
    fanpage = page(db, me, "1234567", "Trang Dưỡng Sinh")
    account = shopee_account(db, me) if has_account else None
    fanpage.shopee_account_id = account.id if account else None
    db.commit()
    video = make_video(db, storage, me, scene_count=1)
    live = post(db, video, me, fanpage)
    fakes.reels[live.remote_id] = {"uploaded": True, "state": "published"}
    row = product(db, me, **fields)
    attach(db, video, row)

    assert affiliate.commission_to(affiliate.page_account(db, fanpage), row) == kind
    post_comments.write(db, live)
    in_comment = "Nồi hầm" in (live.comment_text or "")
    assert in_comment is (kind != "no_link")


def test_each_attached_product_says_whose_commission_it_is_on_each_page(an, binh, db, me, other, storage):
    their_page = page(db, other, "p-binh", "Trang Bình")
    with_account = page(db, other, "p-binh-2", "Trang Bình có tài khoản")
    with_account.shopee_account_id = shopee_account(db, other).id
    db.commit()
    video = make_video(db, storage, other, scene_count=1)
    post(db, video, other, their_page, minutes_ago=2)
    post(db, video, other, with_account, minutes_ago=1)
    saved = product(db, me, "Gối", url="https://s.shopee.vn/cua-an")
    no_link = product(db, me, "Nồi", page_url="https://shopee.vn/product/1/9", shopee_item_id=9)
    tiktok = product(db, me, "Trà", platform="tiktok_shop", url="https://www.tiktok.com/view/product/1")
    for row in (saved, no_link, tiktok):
        attach(db, video, row)

    by_name = {one["name"]: one for one in videos(binh)[video.id]["products"]}
    assert by_name["Gối"]["created_by"] == "Nguyễn Văn An" and by_name["Gối"]["has_saved_link"] is True
    assert by_name["Gối"]["commission"] == [
        {
            "fanpage_id": with_account.id,
            "fanpage_name": "Trang Bình có tài khoản",
            "kind": "page_account",
            "user_id": other.id,
            "user_name": "Trần Bình",
        },
        {
            "fanpage_id": their_page.id,
            "fanpage_name": "Trang Bình",
            "kind": "saved_link",
            "user_id": me.id,
            "user_name": "Nguyễn Văn An",
        },
    ]
    assert [(one["fanpage_name"], one["kind"], one["user_id"]) for one in by_name["Nồi"]["commission"]] == [
        ("Trang Bình có tài khoản", "page_account", other.id),
        ("Trang Bình", "no_link", None),
    ]
    assert by_name["Trà"]["commission"] == [], "TikTok Shop products never go in a Facebook comment"


def test_saving_the_products_answers_with_the_same_owner_fields(an, db, me, storage):
    fanpage = page(db, me, "p-an", "Trang An")
    video = make_video(db, storage, me, scene_count=1)
    post(db, video, me, fanpage)
    row = product(db, me, url="https://s.shopee.vn/a")
    saved = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [row.id]}).json()
    assert saved == videos(an)[video.id]


# The product list and its options


def test_a_product_names_who_added_it_and_whether_it_has_a_saved_link(an, db, me, other):
    product(db, other, "Gối", url="https://s.shopee.vn/a")
    product(db, me, "Nồi", page_url="https://shopee.vn/product/1/2")
    rows = {row["name"]: row for row in an.get(URL).json()}
    assert (rows["Gối"]["created_by"], rows["Gối"]["has_saved_link"]) == ("Trần Bình", True)
    assert (rows["Nồi"]["created_by"], rows["Nồi"]["has_saved_link"]) == ("Nguyễn Văn An", False)


def test_a_product_says_when_its_stars_or_sales_are_under_the_rule(an, db, me):
    product(db, me, "Đủ")
    product(db, me, "Ít sao", rating=4.5)
    product(db, me, "Ít bán", sold=10)
    rows = {row["name"]: row["short_on_counts"] for row in an.get(URL).json()}
    assert rows == {"Đủ": False, "Ít sao": True, "Ít bán": True}


def test_my_topic_groups_are_those_of_the_pages_i_own_and_use(an, db, me, other):
    other_topic = an.post("/api/knowledge/topics", json={"name": "Ăn Lành Sống Khỏe"}).json()["topics"][-1]
    mine_page = page(db, me, "p-an", "Trang An")
    mine_page.knowledge_topic_id = other_topic["id"]
    their_page = page(db, other, "p-binh", "Trang Bình")
    their_page.knowledge_topic_id = first_topic(db).id
    db.commit()

    topics = {topic["name"]: topic["mine"] for topic in an.get(f"{URL}/options").json()["topics"]}
    assert (topics["Sức khỏe"], topics["Ăn Lành Sống Khỏe"]) == (False, True)

    mine_page.active = False
    db.commit()
    assert not any(topic["mine"] for topic in an.get(f"{URL}/options").json()["topics"])


# "Đã dán link tay": the member pasted the links on Facebook, so the app keeps out of the video's comments


def mark_manual(client, video, on=True):
    response = client.put(f"{URL}/videos/{video.id}/manual", json={"manual": on})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_video_marked_as_pasted_by_hand_is_never_commented_by_the_worker(an, db, me, storage, fakes):
    fanpage = page(db, me, "1234567", "Trang Dưỡng Sinh")
    video = make_video(db, storage, me, scene_count=1)
    live = post(db, video, me, fanpage)
    live.auto_comment = True
    db.commit()
    assert post_comments.due_posts(db) == [live]

    row = mark_manual(an, video)
    assert row["manual_comment"] is True and row["posts"][0]["comment"] == "off"
    assert post_comments.due_posts(db) == []
    assert mark_manual(an, video, on=False)["manual_comment"] is False
    assert post_comments.due_posts(db) == [live]


def test_products_attached_to_a_video_pasted_by_hand_do_not_touch_its_comment(an, db, me, storage):
    fanpage = page(db, me, "1234567", "Trang Dưỡng Sinh")
    video = make_video(db, storage, me, scene_count=1)
    live = post(db, video, me, fanpage)
    live.comment_id, live.comment_sent_at = "c-1", datetime.now(UTC)
    db.commit()
    mark_manual(an, video)
    row = product(db, me, url="https://s.shopee.vn/a")

    saved = an.put(f"{URL}/videos/{video.id}", json={"product_ids": [row.id]}).json()
    db.refresh(live)
    assert [one["id"] for one in saved["products"]] == [row.id]
    assert live.comment_requested_at is None, "the app's comment is left as it is"


def test_commenting_now_is_refused_on_a_video_pasted_by_hand(an, db, me, storage):
    fanpage = page(db, me, "1234567", "Trang Dưỡng Sinh")
    video = make_video(db, storage, me, scene_count=1)
    live = post(db, video, me, fanpage)
    mark_manual(an, video)
    refused = an.post(f"/api/posts/{live.id}/comment")
    assert refused.status_code == 409 and "dán link tay" in refused.json()["message"]


def test_each_post_says_how_its_comment_stands_and_the_video_has_its_cover(an, db, me, storage):
    fanpage = page(db, me, "1234567", "Trang Dưỡng Sinh")
    video = make_video(db, storage, me, scene_count=1)
    live = post(db, video, me, fanpage)
    live.comment_id, live.comment_sent_at = "c-1", datetime.now(UTC)
    db.commit()
    row = videos(an)[video.id]
    assert row["manual_comment"] is False and row["posts"][0]["comment"] == "done"
    assert "thumbnail_url" in row
