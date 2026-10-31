import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, FACEBOOK_USER_TOKEN
from sqlalchemy import select

from reels_api import config, fanpages
from reels_api.facebook import FacebookError
from reels_api.models import Fanpage

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


def test_an_unknown_fanpage_is_not_found(an):
    assert an.patch(f"{URL}/999", json={"active": False}).status_code == 404


def test_a_lost_key_asks_for_a_new_token(an, db, fakes):
    (row,) = connect(an).json()
    (config.storage_dir() / fanpages.KEY_FILE).unlink()
    with pytest.raises(FacebookError, match="hãy dán token mới"):
        fanpages.load_page(db, row["id"])


def test_the_key_stays_the_same_between_saves(an, fakes):
    connect(an)
    first = (config.storage_dir() / fanpages.KEY_FILE).read_bytes()
    connect(an)
    assert (config.storage_dir() / fanpages.KEY_FILE).read_bytes() == first
