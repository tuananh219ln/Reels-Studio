from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, FACEBOOK_USER_TOKEN
from sqlalchemy import select

from reels_api import config, crypto, fanpages
from reels_api.facebook import FacebookError
from reels_api.models import (
    AffiliateAccount,
    Fanpage,
    FanpageFollowers,
    FanpageInsights,
    Publication,
    TikTokConnection,
)

URL = "/api/fanpages"
PAGE = {"id": FACEBOOK_PAGE, "name": "Trang Dưỡng Sinh"}


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def connect(an):
    return an.post(URL, json={"token": FACEBOOK_USER_TOKEN, "page_ids": [FACEBOOK_PAGE]})


def test_fanpages_need_a_login(client):
    assert client.get(URL).status_code == 401


def test_a_user_token_lists_its_pages_and_saves_nothing(an, fakes):
    listed = an.post(f"{URL}/lookup", json={"token": f" {FACEBOOK_USER_TOKEN} "})
    assert listed.json() == {"pages": [{"page_id": FACEBOOK_PAGE, "name": "Trang Dưỡng Sinh", "can_post": True}]}
    assert FACEBOOK_TOKEN not in listed.text and FACEBOOK_USER_TOKEN not in listed.text
    assert an.get(URL).json() == []


def test_a_pages_own_token_lists_that_page(an, fakes):
    assert [page["page_id"] for page in an.post(f"{URL}/lookup", json={"token": FACEBOOK_TOKEN}).json()["pages"]] == [
        FACEBOOK_PAGE
    ]


def test_a_page_the_token_cannot_post_to_is_marked_and_refused(an, fakes):
    fakes.facebook_pages = [PAGE | {"tasks": ["ANALYZE"]}]
    (page,) = an.post(f"{URL}/lookup", json={"token": FACEBOOK_USER_TOKEN}).json()["pages"]
    assert page["can_post"] is False
    refused = connect(an)
    assert (refused.status_code, refused.json()["message"]) == (422, "Token không có quyền đăng lên Page đã chọn")


def test_a_token_managing_no_page_says_what_to_do(an, fakes):
    fakes.facebook_pages = []
    refused = an.post(f"{URL}/lookup", json={"token": FACEBOOK_USER_TOKEN})
    assert refused.status_code == 422 and refused.json()["message"].startswith("Token không quản lý Page nào")


def test_a_bad_token_is_refused_with_its_reason(an, fakes):
    refused = an.post(f"{URL}/lookup", json={"token": "het-han"})
    assert refused.status_code == 422 and "hết hạn" in refused.json()["message"]


@pytest.mark.parametrize(
    ("token", "reason"),
    [
        ("   ", "Hãy dán token"),
        ("abc\ndef", "Token không hợp lệ, hãy chép lại đúng một dòng token"),
        ("a" * 1001, "Token không hợp lệ, hãy chép lại đúng một dòng token"),
    ],
)
def test_a_malformed_token_never_reaches_facebook(an, token, reason):
    refused = an.post(f"{URL}/lookup", json={"token": token})
    assert (refused.status_code, refused.json()["message"]) == (422, reason)


def test_connecting_keeps_the_pages_own_token_encrypted_and_shows_only_its_tail(an, db, fakes):
    saved = connect(an)
    assert saved.status_code == 201
    (row,) = saved.json()
    assert (row["page_id"], row["name"], row["active"]) == (FACEBOOK_PAGE, "Trang Dưỡng Sinh", True)
    assert row["token_tail"] == FACEBOOK_TOKEN[-4:] and row["updated_by"]
    assert FACEBOOK_TOKEN not in saved.text and FACEBOOK_USER_TOKEN not in saved.text
    assert FACEBOOK_TOKEN not in db.scalar(select(Fanpage)).token_encrypted
    assert fanpages.load_page(db, row["id"]).token == FACEBOOK_TOKEN, "the Page's token, not the pasted user token"
    assert FACEBOOK_TOKEN not in repr(fanpages.load_page(db, row["id"]))


def test_several_pages_connect_from_one_token(an, fakes):
    fakes.facebook_pages = [
        PAGE | {"tasks": ["CREATE_CONTENT"]},
        {"id": "222", "name": "Trang Hai", "tasks": ["CREATE_CONTENT"]},
    ]
    rows = an.post(URL, json={"token": FACEBOOK_USER_TOKEN, "page_ids": [FACEBOOK_PAGE, "222"]}).json()
    assert {row["page_id"] for row in rows} == {FACEBOOK_PAGE, "222"}


def test_a_page_id_the_token_does_not_manage_is_refused(an, db, fakes):
    refused = an.post(URL, json={"token": FACEBOOK_USER_TOKEN, "page_ids": ["61575034297904"]})
    assert (refused.status_code, refused.json()["message"]) == (422, "Token không có quyền đăng lên Page đã chọn")
    assert db.scalar(select(Fanpage)) is None


def test_saving_needs_a_chosen_page(an, fakes):
    refused = an.post(URL, json={"token": FACEBOOK_USER_TOKEN, "page_ids": []})
    assert (refused.status_code, refused.json()["message"]) == (422, "Hãy chọn ít nhất một Page")


def test_connecting_a_page_again_updates_it(an, db, fakes):
    connect(an)
    assert len(connect(an).json()) == 1


def test_a_new_token_must_reach_this_very_page(an, db, fakes):
    (row,) = connect(an).json()
    fakes.facebook_pages = [{"id": "222", "name": "Trang Hai", "tasks": ["CREATE_CONTENT"]}]
    refused = an.put(f"{URL}/{row['id']}/token", json={"token": FACEBOOK_USER_TOKEN})
    assert (refused.status_code, refused.json()["message"]) == (
        422,
        "Token mới không có quyền đăng lên Page “Trang Dưỡng Sinh”",
    )
    assert fanpages.load_page(db, row["id"]).token == FACEBOOK_TOKEN


def test_a_new_token_replaces_the_old_one_and_reactivates_the_page(an, db, fakes):
    (row,) = connect(an).json()
    an.patch(f"{URL}/{row['id']}", json={"active": False})
    (updated,) = an.put(f"{URL}/{row['id']}/token", json={"token": FACEBOOK_TOKEN}).json()
    assert updated["active"] is True


def test_stopping_a_page_takes_it_off_the_video_page_and_blocks_posting(an, db, me, storage, fakes):
    (row,) = connect(an).json()
    video = make_video(db, storage, me)
    assert [page["name"] for page in an.get(f"/api/videos/{video.id}").json()["fanpages"]] == ["Trang Dưỡng Sinh"]

    (stopped,) = an.patch(f"{URL}/{row['id']}", json={"active": False}).json()
    assert stopped["active"] is False
    assert an.get(f"/api/videos/{video.id}").json()["fanpages"] == []
    with pytest.raises(FacebookError, match="đang ngừng dùng"):
        fanpages.load_page(db, row["id"])
    assert an.patch(f"{URL}/{row['id']}", json={"active": True}).json()[0]["active"] is True


def test_the_video_page_names_who_connected_each_page(an, db, me, storage, fakes):
    connect(an)
    video = make_video(db, storage, me)
    (listed,) = an.get(f"/api/videos/{video.id}").json()["fanpages"]
    assert (listed["name"], listed["owner"]) == ("Trang Dưỡng Sinh", "Nguyễn Văn An")


def test_an_unknown_fanpage_is_not_found(an):
    assert an.patch(f"{URL}/999", json={"active": False}).status_code == 404


def test_a_lost_key_asks_for_a_new_token(an, db, fakes):
    (row,) = connect(an).json()
    (config.storage_dir() / crypto.KEY_FILE).unlink()
    with pytest.raises(FacebookError, match="hãy dán token mới"):
        fanpages.load_page(db, row["id"])


def test_the_key_stays_the_same_between_saves(an, fakes):
    connect(an)
    first = (config.storage_dir() / crypto.KEY_FILE).read_bytes()
    connect(an)
    assert (config.storage_dir() / crypto.KEY_FILE).read_bytes() == first


# Deleting a Page


def test_a_stopped_page_never_posted_to_can_be_deleted_with_its_numbers(an, db, fakes):
    (row,) = connect(an).json()
    assert row["posts"] == 0
    page = db.get(Fanpage, row["id"])
    fanpages.check(db, page)
    an.patch(f"{URL}/{row['id']}", json={"active": False})
    assert an.delete(f"{URL}/{row['id']}").json() == []
    db.expire_all()
    assert db.scalars(select(Fanpage)).all() == []
    assert db.scalars(select(FanpageFollowers)).all() == [] and db.scalars(select(FanpageInsights)).all() == []


def test_a_page_in_use_must_be_stopped_before_it_is_deleted(an, fakes):
    (row,) = connect(an).json()
    refused = an.delete(f"{URL}/{row['id']}")
    assert (refused.status_code, refused.json()["message"]) == (409, "Hãy ngừng dùng Fanpage trước khi xóa")


def test_a_page_with_posts_is_kept_for_their_history(an, db, me, storage, fakes):
    (row,) = connect(an).json()
    video = make_video(db, storage, me)
    db.add(
        Publication(video_id=video.id, platform="facebook", created_by_id=me.id, fanpage_id=row["id"], status="deleted")
    )
    db.commit()
    (stopped,) = an.patch(f"{URL}/{row['id']}", json={"active": False}).json()
    assert stopped["posts"] == 1
    refused = an.delete(f"{URL}/{row['id']}")
    assert refused.status_code == 409
    assert refused.json()["message"] == "Fanpage đã có 1 bài đăng nên được giữ lại để xem lịch sử; cứ để ngừng dùng"


def test_deleting_an_unknown_page(an):
    assert an.delete(f"{URL}/999").status_code == 404


# The Page's TikTok account


def tiktok_account(db, me, name="TikTok của An", platform="tiktok", active=True):
    account = AffiliateAccount(platform=platform, owner_id=me.id, name=name, active=active)
    db.add(account)
    db.commit()
    return account


def connect_tiktok(db, account, me):
    moment = datetime.now(UTC)
    db.add(
        TikTokConnection(
            owner_id=me.id,
            affiliate_account_id=account.id,
            open_id="tiktok-open-id",
            username="anlanhsk",
            display_name="An Lành SK",
            access_token_encrypted=crypto.encrypt("fake-access"),
            refresh_token_encrypted=crypto.encrypt("fake-refresh"),
            access_expires_at=moment + timedelta(hours=2),
            refresh_expires_at=moment + timedelta(days=365),
            scopes="user.info.basic,video.upload,video.publish",
        )
    )
    db.commit()


def test_a_pages_owner_sets_its_tiktok_account(an, db, me, fakes):
    (row,) = connect(an).json()
    account = tiktok_account(db, me)
    (updated,) = an.put(f"{URL}/{row['id']}/tiktok-account", json={"account_id": account.id}).json()
    assert updated["tiktok_account"] == {"id": account.id, "name": "TikTok của An", "connected": False}
    assert db.get(Fanpage, row["id"]).tiktok_account_id == account.id


def test_a_connected_tiktok_account_shows_connected_on_the_page(an, db, me, fakes):
    (row,) = connect(an).json()
    account = tiktok_account(db, me)
    connect_tiktok(db, account, me)
    (updated,) = an.put(f"{URL}/{row['id']}/tiktok-account", json={"account_id": account.id}).json()
    assert updated["tiktok_account"]["connected"] is True


def test_clearing_a_pages_tiktok_account(an, db, me, fakes):
    (row,) = connect(an).json()
    account = tiktok_account(db, me)
    an.put(f"{URL}/{row['id']}/tiktok-account", json={"account_id": account.id})
    (updated,) = an.put(f"{URL}/{row['id']}/tiktok-account", json={"account_id": None}).json()
    assert updated["tiktok_account"] is None
    assert db.get(Fanpage, row["id"]).tiktok_account_id is None


def test_a_shopee_account_cannot_be_the_pages_tiktok_account(an, db, me, fakes):
    (row,) = connect(an).json()
    account = tiktok_account(db, me, name="Shopee của An", platform="shopee")
    refused = an.put(f"{URL}/{row['id']}/tiktok-account", json={"account_id": account.id})
    assert (refused.status_code, refused.json()["message"]) == (422, "Hãy chọn một tài khoản TikTok của bạn")
    assert db.get(Fanpage, row["id"]).tiktok_account_id is None


def test_an_inactive_tiktok_account_is_refused(an, db, me, fakes):
    (row,) = connect(an).json()
    account = tiktok_account(db, me, active=False)
    refused = an.put(f"{URL}/{row['id']}/tiktok-account", json={"account_id": account.id})
    assert (refused.status_code, refused.json()["message"]) == (422, "Tài khoản “TikTok của An” đang ngừng dùng")


def test_only_the_pages_owner_sets_its_tiktok_account(an, client, db, me, fakes):
    (row,) = connect(an).json()
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    login(client, "binh@doi.vn")
    account = tiktok_account(db, other)
    refused = client.put(f"{URL}/{row['id']}/tiktok-account", json={"account_id": account.id})
    assert (refused.status_code, refused.json()["message"]) == (
        403,
        "Chỉ chủ của Fanpage mới gắn được tài khoản TikTok",
    )


def test_an_unknown_fanpage_has_no_tiktok_account(an):
    assert an.put(f"{URL}/999/tiktok-account", json={"account_id": None}).status_code == 404


def test_a_video_carries_its_pages_tiktok_account(an, db, me, storage, fakes):
    (row,) = connect(an).json()
    account = tiktok_account(db, me)
    page = db.get(Fanpage, row["id"])
    page.knowledge_topic_id = first_topic(db).id
    page.tiktok_account_id = account.id
    db.commit()
    video = make_video(db, storage, me)
    (listed,) = an.get(f"/api/videos/{video.id}").json()["fanpages"]
    assert listed["tiktok_account_id"] == account.id


def test_a_video_whose_page_picked_no_tiktok_account_has_none(an, db, me, storage, fakes):
    (row,) = connect(an).json()
    page = db.get(Fanpage, row["id"])
    page.knowledge_topic_id = first_topic(db).id
    db.commit()
    video = make_video(db, storage, me)
    (listed,) = an.get(f"/api/videos/{video.id}").json()["fanpages"]
    assert listed["tiktok_account_id"] is None
