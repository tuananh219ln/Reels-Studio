"""Posts on YouTube Shorts and Instagram Reels, made by hand from any video's MP4 and recorded with their link."""

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api.models import Publication

POSTS = "/api/manual-posts"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def binh(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


def rendered(db, storage, user, platform="facebook"):
    video = make_video(db, storage, user, scene_count=1)
    video.platform, video.mp4_key = platform, f"videos/{video.id}/video.mp4"
    db.commit()
    return video


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("youtube", "https://youtube.com/shorts/AbCdEf12345"),
        ("youtube", "https://www.youtube.com/watch?v=AbCdEf12345"),
        ("youtube", "https://youtu.be/AbCdEf12345"),
        ("instagram", "https://www.instagram.com/reel/C1a2B3c4D5e/"),
        ("instagram", "https://www.instagram.com/an.duongsinh/reel/C1a2B3c4D5e"),
    ],
)
def test_a_facebook_video_posted_by_hand_elsewhere_is_recorded(an, db, me, storage, platform, url):
    video = rendered(db, storage, me)

    answer = an.post(f"{POSTS}/videos/{video.id}", json={"platform": platform, "url": f"  {url} "})

    assert answer.status_code == 201, answer.text
    [post] = answer.json()["manual_posts"]
    assert (post["platform"], post["url"], post["created_by"]) == (platform, url, me.name)
    stored = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (stored.status, stored.remote_mp4_key, stored.remote_id) == ("published", video.mp4_key, None)
    # It is not a Facebook post: the Facebook lists leave it out.
    assert answer.json()["publications"] == []


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("youtube", "http://youtube.com/shorts/AbCdEf12345"),
        ("youtube", "https://evil.vn/shorts/AbCdEf12345"),
        ("youtube", "https://youtube.com/@kenh"),
        ("instagram", "https://www.instagram.com/an.duongsinh/"),
        ("instagram", "https://www.tiktok.com/@a/video/1"),
        ("vimeo", "https://vimeo.com/1"),
        ("facebook", "https://www.facebook.com/reel/1"),
    ],
)
def test_wrong_links_and_platforms_are_refused(an, db, me, storage, platform, url):
    video = rendered(db, storage, me)
    answer = an.post(f"{POSTS}/videos/{video.id}", json={"platform": platform, "url": url})
    assert answer.status_code == 422
    assert db.scalar(select(Publication).where(Publication.video_id == video.id)) is None


def test_a_video_without_its_mp4_has_nothing_to_post(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    answer = an.post(f"{POSTS}/videos/{video.id}", json={"platform": "youtube", "url": "https://youtu.be/AbCdEf12345"})
    assert answer.status_code == 422 and answer.json()["message"] == "Video chưa render MP4 để đăng"


def test_only_the_member_who_recorded_a_post_removes_it(an, db, me, storage, binh, client):
    video = rendered(db, storage, me, platform="tiktok")
    post_id = an.post(
        f"{POSTS}/videos/{video.id}",
        json={"platform": "instagram", "url": "https://www.instagram.com/reel/C1a2B3c4D5e/"},
    ).json()["manual_posts"][0]["id"]

    login(client, "binh@doi.vn")
    assert client.delete(f"{POSTS}/{post_id}").status_code == 403
    login(client)
    removed = client.delete(f"{POSTS}/{post_id}")

    assert removed.status_code == 200 and removed.json()["manual_posts"] == []
    assert client.delete(f"{POSTS}/{post_id}").status_code == 404


def test_the_video_list_says_every_platform_the_video_is_out_on(an, db, me, storage):
    video = rendered(db, storage, me)
    an.post(f"{POSTS}/videos/{video.id}", json={"platform": "youtube", "url": "https://youtu.be/AbCdEf12345"})
    row = next(row for row in an.get("/api/videos").json() if row["id"] == video.id)
    assert row["posted_on"] == ["youtube"]


def test_the_video_list_links_each_platform_to_its_post(an, db, me, storage):
    from reels_api.models import Publication

    video = rendered(db, storage, me)
    an.post(f"{POSTS}/videos/{video.id}", json={"platform": "youtube", "url": "https://youtu.be/AbCdEf12345"})
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            status="published",
            remote_id="123456789012",
            created_by_id=me.id,
        )
    )
    db.commit()
    row = next(row for row in an.get("/api/videos").json() if row["id"] == video.id)
    assert row["posted_links"] == {
        "facebook": "https://www.facebook.com/reel/123456789012",
        "youtube": "https://youtu.be/AbCdEf12345",
    }
    assert an.get(f"/api/videos/{video.id}").json()["posted_links"] == row["posted_links"]
