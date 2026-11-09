"""Only a Page's owner posts to it, and the owner may take any post on their Page down (2026-11-09, option A): the
commission of a post belongs to its Page's owner, so a teammate cannot post on a Page they do not own."""

import pytest
from conftest import client_for, login, make_user, make_video
from test_article_posts import add_article
from test_fanpage_checks import add_page
from test_publish import add_mp4

from reels_api.models import Publication


@pytest.fixture
def an_user(db):
    return make_user(db)


@pytest.fixture
def binh_user(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


@pytest.fixture
def an(client, an_user):
    login(client)
    return client


@pytest.fixture
def binh(app, binh_user):
    client = client_for(app)
    login(client, email="binh@doi.vn")
    return client


def not_page_owner(response, message: str) -> None:
    assert response.status_code == 403, response.text
    assert (response.json()["code"], response.json()["message"]) == ("not_page_owner", message)


TEAMMATES_PAGE = "Chỉ chủ Page “Trang Dưỡng Sinh” (Nguyễn Văn An) mới đăng được lên Page này"
NO_OWNER = "Page “Trang Dưỡng Sinh” chưa có chủ: hãy bấm “Nhận Page” ở Quản lý Page rồi đăng"


def test_a_video_is_posted_only_to_a_page_its_poster_owns(an, binh, db, an_user, binh_user, storage):
    page = add_page(db, an_user)
    video = make_video(db, storage, binh_user, scene_count=1)
    add_mp4(db, storage, video)
    not_page_owner(binh.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page.id}), TEAMMATES_PAGE)
    assert db.query(Publication).count() == 0
    # The Page's owner posts anyone's video to it, as before.
    assert an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page.id}).status_code == 200


def test_a_page_with_no_owner_is_claimed_before_posting(an, db, an_user, storage):
    page = add_page(db, an_user)
    page.owner_id = None
    db.commit()
    video = make_video(db, storage, an_user, scene_count=1)
    add_mp4(db, storage, video)
    not_page_owner(an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page.id}), NO_OWNER)
    article = add_article(db, an_user)
    not_page_owner(an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": page.id}), NO_OWNER)


def test_an_article_is_posted_only_to_a_page_its_poster_owns(an, binh, db, an_user, binh_user):
    page = add_page(db, an_user)
    article = add_article(db, binh_user)
    not_page_owner(binh.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": page.id}), TEAMMATES_PAGE)
    assert an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": page.id}).status_code == 200


def test_a_video_goes_only_into_the_queue_of_a_page_the_member_owns(an, binh, db, an_user, binh_user, storage):
    page = add_page(db, an_user)
    video = make_video(db, storage, binh_user, scene_count=1)
    add_mp4(db, storage, video)
    not_page_owner(binh.post("/api/queue", json={"video_id": video.id, "fanpage_id": page.id}), TEAMMATES_PAGE)
    assert an.post("/api/queue", json={"video_id": video.id, "fanpage_id": page.id}).status_code == 200


def test_the_pages_owner_takes_down_any_post_on_their_page(an, binh, db, an_user, binh_user, storage):
    """Binh posted on An's Page before this rule: An, the Page's owner, may take it down, as Binh still may."""
    page = add_page(db, an_user)
    other = add_page(db, binh_user, page_id="222", name="Trang Bình")
    video = make_video(db, storage, binh_user, scene_count=1)
    article = add_article(db, binh_user)
    posts = [
        Publication(video_id=video.id, platform="facebook", fanpage_id=page.id, created_by_id=binh_user.id),
        Publication(article_id=article.id, platform="facebook", fanpage_id=page.id, created_by_id=binh_user.id),
    ]
    db.add_all(posts)
    db.commit()
    assert an.post(f"/api/posts/{posts[0].id}/take-down").status_code == 200
    assert an.post(f"/api/articles/posts/{posts[1].id}/take-down").status_code == 200
    # A post on someone else's Page is still not An's to take down.
    theirs = Publication(video_id=video.id, platform="facebook", fanpage_id=other.id, created_by_id=binh_user.id)
    db.add(theirs)
    db.commit()
    refused = an.post(f"/api/posts/{theirs.id}/take-down")
    assert (refused.status_code, refused.json()["code"]) == (403, "not_owner")


def test_the_article_editor_offers_only_my_pages(an, binh, db, an_user, binh_user):
    add_page(db, an_user)
    add_page(db, binh_user, page_id="222", name="Trang Bình")
    assert [page["name"] for page in an.get("/api/articles/options").json()["fanpages"]] == ["Trang Dưỡng Sinh"]
    assert [page["name"] for page in binh.get("/api/articles/options").json()["fanpages"]] == ["Trang Bình"]
