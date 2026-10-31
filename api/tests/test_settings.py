import pytest

from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from reels_api import config, page_settings
from reels_api.facebook import FacebookError
from reels_api.models import Setting

URL = "/api/settings/facebook"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_settings_need_a_login(client):
    assert client.get(URL).status_code == 401


def test_the_token_is_encrypted_and_never_comes_back(an, db):
    saved = an.put(URL, json={"page_id": f" {FACEBOOK_PAGE} ", "token": f" {FACEBOOK_TOKEN}\n"})
    assert saved.json() == {"page_id": FACEBOOK_PAGE, "has_token": True}
    assert an.get(URL).json() == {"page_id": FACEBOOK_PAGE, "has_token": True}
    assert FACEBOOK_TOKEN not in saved.text
    assert FACEBOOK_TOKEN not in str(db.get(Setting, page_settings.TOKEN).value)
    page = page_settings.load_page(db)
    assert (page.id, page.token) == (FACEBOOK_PAGE, FACEBOOK_TOKEN)
    assert FACEBOOK_TOKEN not in repr(page)


def test_an_empty_token_keeps_the_saved_one(an, db):
    an.put(URL, json={"page_id": FACEBOOK_PAGE, "token": FACEBOOK_TOKEN})
    assert an.put(URL, json={"page_id": "7654321", "token": ""}).status_code == 200
    page = page_settings.load_page(db)
    assert (page.id, page.token) == ("7654321", FACEBOOK_TOKEN)


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"page_id": "trang-cua-toi", "token": "abc"}, "Page ID chỉ gồm chữ số"),
        ({"page_id": "", "token": "abc"}, "Page ID chỉ gồm chữ số"),
        ({"page_id": "123", "token": "abc\ndef"}, "Token không hợp lệ, hãy chép lại đúng một dòng token"),
        ({"page_id": "123", "token": "a" * 1001}, "Token không hợp lệ, hãy chép lại đúng một dòng token"),
        ({"page_id": "123", "token": ""}, "Hãy nhập token"),
    ],
)
def test_bad_values_are_refused(an, body, reason):
    refused = an.put(URL, json=body)
    assert (refused.status_code, refused.json()["message"]) == (422, reason)


def test_the_connection_check_names_the_page(an, fakes):
    an.put(URL, json={"page_id": FACEBOOK_PAGE, "token": FACEBOOK_TOKEN})
    assert an.post(f"{URL}/test").json() == {"page_name": "Trang Dưỡng Sinh"}
    assert fakes.reels == {}, "nothing is posted"


def test_the_connection_check_explains_a_bad_token(an, fakes):
    an.put(URL, json={"page_id": FACEBOOK_PAGE, "token": "het-han"})
    refused = an.post(f"{URL}/test")
    assert refused.status_code == 422
    assert "hết hạn" in refused.json()["message"]


def test_the_connection_check_without_settings_says_what_is_missing(an):
    assert an.post(f"{URL}/test").json()["message"] == "Chưa nhập Page ID và token, hãy vào Cài đặt"


def test_a_lost_key_asks_for_the_token_again(an, db):
    an.put(URL, json={"page_id": FACEBOOK_PAGE, "token": FACEBOOK_TOKEN})
    (config.storage_dir() / page_settings.KEY_FILE).unlink()
    with pytest.raises(FacebookError, match="Không đọc được token đã lưu"):
        page_settings.load_page(db)


def test_a_new_key_keeps_working_for_the_next_process(an, db):
    an.put(URL, json={"page_id": FACEBOOK_PAGE, "token": FACEBOOK_TOKEN})
    first = (config.storage_dir() / page_settings.KEY_FILE).read_bytes()
    an.put(URL, json={"page_id": FACEBOOK_PAGE, "token": "token-moi"})
    assert (config.storage_dir() / page_settings.KEY_FILE).read_bytes() == first


def test_the_video_says_whether_facebook_is_connected(an, db, me, storage):
    video = make_video(db, storage, me)
    assert an.get(f"/api/videos/{video.id}").json()["facebook_ready"] is False
    an.put(URL, json={"page_id": FACEBOOK_PAGE, "token": FACEBOOK_TOKEN})
    assert an.get(f"/api/videos/{video.id}").json()["facebook_ready"] is True
