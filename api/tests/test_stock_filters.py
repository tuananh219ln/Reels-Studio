"""The stock picker's filters (orientation, photos already in the video, too small) and Pixabay's error messages."""

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api.models import Scene


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scenes_of(db, video) -> list[Scene]:
    return db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()


# --- Pixabay's errors ---


def test_cloudflare_blocking_pixabay_says_so_instead_of_a_rate_limit(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    fakes.pixabay_mode = "cloudflare_block"
    refused = an.get(f"/api/scenes/{scenes_of(db, video)[0].id}/stock", params={"q": "sữa chua", "source": "pixabay"})
    assert refused.status_code == 502
    message = refused.json()["message"]
    assert "chặn" in message and "nguồn khác" in message and "giới hạn lượt" not in message


def test_a_real_rate_limit_still_says_to_wait(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    fakes.pixabay_mode = "rate_limit"
    refused = an.get(f"/api/scenes/{scenes_of(db, video)[0].id}/stock", params={"q": "sữa chua", "source": "pixabay"})
    assert refused.status_code == 502 and "giới hạn lượt tìm" in refused.json()["message"]


# --- Filters ---


def search(an, scene_id, **params):
    return an.get(f"/api/scenes/{scene_id}/stock", params={"q": "sữa chua", **params})


def asked(fakes, source) -> dict:
    return [query for name, query in fakes.stock_searches if name == source][-1]


@pytest.mark.parametrize(
    ("orientation", "pixabay", "pexels", "openverse"),
    [
        (None, "vertical", "portrait", "tall"),  # tall photos by default: the 9:16 frame crops least of them
        ("vertical", "vertical", "portrait", "tall"),
        ("square", None, "square", "square"),
        ("all", None, None, None),
    ],
)
def test_each_source_is_asked_for_the_chosen_orientation(
    an, db, me, storage, fakes, orientation, pixabay, pexels, openverse
):
    scene_id = scenes_of(db, make_video(db, storage, me))[0].id
    params = {} if orientation is None else {"orientation": orientation}
    for source in ("pixabay", "pexels", "openverse"):
        assert search(an, scene_id, source=source, **params).status_code == 200
    assert asked(fakes, "pixabay").get("orientation") == pixabay
    assert asked(fakes, "pexels").get("orientation") == pexels
    assert asked(fakes, "openverse").get("aspect_ratio") == openverse


def test_an_unknown_orientation_is_refused(an, db, me, storage, fakes):
    scene_id = scenes_of(db, make_video(db, storage, me))[0].id
    refused = search(an, scene_id, source="pixabay", orientation="diagonal")
    assert refused.status_code == 422 and "Hướng ảnh" in refused.json()["message"]


def test_results_of_the_wrong_shape_or_too_small_are_left_out(an, db, me, storage, fakes):
    scene_id = scenes_of(db, make_video(db, storage, me))[0].id
    fakes.pixabay_results["sữa chua"] = ["tall", "square", "wide", "tiny", "unknown"]
    fakes.pixabay_sizes.update({"tall": (3000, 4500), "square": (2000, 2000), "wide": (4000, 2500), "tiny": (300, 450)})

    def names(**params):
        hits = search(an, scene_id, source="pixabay", **params).json()["hits"]
        return [hit["url"].rsplit("/", 1)[1].removesuffix(".jpg") for hit in hits]

    # A result without a size is kept: nothing says it is wrong.
    assert names() == ["tall", "unknown"]
    assert names(orientation="square") == ["square", "unknown"]
    assert names(orientation="all") == ["tall", "square", "wide", "unknown"]


def test_photos_already_in_the_video_are_hidden_unless_asked_for(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    first, second = scenes_of(db, video)[:2]
    second.image_source = fakes.image_url("b")
    db.commit()
    fakes.pixabay_results["sữa chua"] = ["a", "b", "c"]
    shown = [hit["url"] for hit in search(an, first.id, source="pixabay").json()["hits"]]
    assert shown == [fakes.image_url("a"), fakes.image_url("c")]
    every = search(an, first.id, source="pixabay", hide_used="false").json()["hits"]
    assert [hit["url"] for hit in every] == [fakes.image_url(name) for name in "abc"]


def test_a_result_of_a_filtered_search_can_be_chosen(an, db, me, storage, fakes):
    scene = scenes_of(db, make_video(db, storage, me))[0]
    fakes.pixabay_results["sữa chua"] = ["sq"]
    fakes.pixabay_sizes["sq"] = (2000, 2000)
    assert search(an, scene.id, source="pixabay", orientation="square").json()["hits"]
    chosen = an.post(
        f"/api/scenes/{scene.id}/stock",
        json={"source": "pixabay", "keyword": "sữa chua", "url": fakes.image_url("sq"), "orientation": "square"},
    )
    assert chosen.status_code == 200, chosen.text
    db.expire_all()
    assert db.get(Scene, scene.id).image_source == fakes.image_url("sq")


def test_find_image_takes_a_tall_photo_not_used_by_another_scene(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    first, second = scenes_of(db, video)[:2]
    keyword = first.keywords_en[0] if first.keywords_en else first.keywords[0]
    fakes.pixabay_results[keyword] = ["used", "fresh"]
    second.image_source = fakes.image_url("used")
    db.commit()
    found = an.post(f"/api/scenes/{first.id}/find-image", params={"source": "pixabay"})
    assert found.status_code == 200, found.text
    db.expire_all()
    assert db.get(Scene, first.id).image_source == fakes.image_url("fresh")
    assert asked(fakes, "pixabay").get("orientation") == "vertical"
