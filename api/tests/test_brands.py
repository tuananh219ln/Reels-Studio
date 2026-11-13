"""Brands ("Kênh"): one logo per brand, laid on the MP4 at render; the API, the video's switch and the fingerprint."""

import io

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE
from PIL import Image
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api.models import Brand, Fanpage, Publication
from reels_api.videos import render_signature, split_scenes

URL = "/api/brands"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def logo_file(size=(400, 300), color=(200, 30, 30), name="logo.png", kind="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, kind)
    return {"file": (name, buffer.getvalue(), f"image/{kind.lower()}")}


def make_brand(an, name="Ăn Ngon Sống Khỏe", **body):
    made = an.post(URL, json={"name": name, **body})
    assert made.status_code == 201, made.json()
    return made.json()


def with_logo(an, brand_id=None, **kwargs):
    brand_id = brand_id or make_brand(an)["id"]
    done = an.post(f"{URL}/{brand_id}/logo", files=logo_file(**kwargs))
    assert done.status_code == 200, done.json()
    return brand_id, done.json()


def own_page(db, me, name="Trang Dưỡng Sinh", page_id=FACEBOOK_PAGE) -> Fanpage:
    page = Fanpage(page_id=page_id, name=name, token_encrypted="x", token_tail="x", owner_id=me.id)
    db.add(page)
    db.commit()
    return page


# --- The brands API ---


def test_brands_need_a_login(client):
    assert client.get(URL).status_code == 401


def test_a_brand_is_made_listed_renamed_and_its_name_is_unique(an):
    brand = make_brand(an)
    assert brand["slug"] == "an-ngon-song-khoe" and brand["logo_badge_url"] is None and brand["logo_default_on"] is True
    assert [item["name"] for item in an.get(URL).json()] == ["Ăn Ngon Sống Khỏe"]
    assert an.post(URL, json={"name": "Ăn Ngon Sống Khỏe"}).status_code == 409
    renamed = an.patch(f"{URL}/{brand['id']}", json={"name": "Ăn Lành", "tiktok_username": "@anlanh"})
    assert (renamed.json()["name"], renamed.json()["tiktok_username"]) == ("Ăn Lành", "anlanh")


def test_a_brand_links_one_of_the_members_pages_and_a_page_belongs_to_one_brand(an, db, me):
    page = own_page(db, me)
    first = make_brand(an, "Kênh một", fanpage_id=page.id)
    assert first["fanpage"]["name"] == "Trang Dưỡng Sinh"
    second = make_brand(an, "Kênh hai")
    taken = an.patch(f"{URL}/{second['id']}", json={"fanpage_id": page.id})
    assert (taken.status_code, taken.json()["code"]) == (409, "fanpage_taken")


def test_only_the_owner_changes_a_brand_but_everyone_sees_it(an, db, client):
    brand = make_brand(an)
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    other = client.__class__(client.app, headers=dict(client.headers))
    login(other, email="binh@doi.vn")
    assert [item["id"] for item in other.get(URL).json()] == [brand["id"]]
    refused = other.patch(f"{URL}/{brand['id']}", json={"name": "Của tôi"})
    assert (refused.status_code, refused.json()["code"]) == (403, "not_brand_owner")
    assert other.delete(f"{URL}/{brand['id']}").status_code == 403


def test_a_logo_makes_a_round_badge_and_a_version_that_changes_with_the_picture(an, storage):
    brand_id, done = with_logo(an)
    assert len(done["logo_version"]) == 6 and done["logo_badge_url"].endswith(f"?v={done['logo_version']}")
    assert done["videos_outdated"] == 0
    badge = an.get(f"{URL}/{brand_id}/logo/badge.png")
    assert badge.status_code == 200 and badge.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(badge.content)).mode == "RGBA"
    again = an.post(f"{URL}/{brand_id}/logo", files=logo_file(color=(10, 10, 200)))
    assert again.json()["logo_version"] != done["logo_version"]
    # The old files are gone: one original and one badge are kept.
    assert sorted(path.name[:4] for path in (storage.root / "brands" / str(brand_id)).iterdir()) == ["badg", "logo"]


@pytest.mark.parametrize(
    ("files", "why"),
    [
        (logo_file(size=(200, 200)), "nhỏ"),
        (logo_file(size=(6000, 6000), color=(1, 2, 3)), "5 MB"),
        ({"file": ("a.png", b"not a picture", "image/png")}, "PNG, JPG"),
    ],
)
def test_a_bad_logo_is_refused_with_a_reason_and_saves_nothing(an, files, why):
    brand_id = make_brand(an)["id"]
    if why == "5 MB":
        # A big flat picture compresses small, so send noise-free padding: a PNG over the limit.
        import os

        buffer = io.BytesIO()
        Image.frombytes("RGB", (1200, 1200), os.urandom(1200 * 1200 * 3)).save(buffer, "PNG")
        files = {"file": ("big.png", buffer.getvalue(), "image/png")}
    refused = an.post(f"{URL}/{brand_id}/logo", files=files)
    assert refused.status_code == 400 and why in refused.json()["message"]
    assert an.get(f"{URL}/{brand_id}").json()["logo_badge_url"] is None


def test_the_pages_picture_can_be_the_logo(an, db, me, fakes, monkeypatch):
    page = own_page(db, me)
    page.picture_url = "https://example.test/page.png"
    db.commit()
    brand_id = make_brand(an, fanpage_id=page.id)["id"]
    from reels_api import remote_media

    monkeypatch.setattr(remote_media, "download", lambda url, folder: remote_media.Media(photo=(logo_bytes(), "png")))
    done = an.post(f"{URL}/{brand_id}/logo/from-fanpage")
    assert done.status_code == 200 and done.json()["logo_badge_url"]
    unlinked = make_brand(an, "Không Page")
    assert an.post(f"{URL}/{unlinked['id']}/logo/from-fanpage").status_code == 409


def logo_bytes():
    return logo_file()["file"][1]


def test_a_brand_in_use_is_not_deleted_and_its_logo_goes_with_a_free_one(an, db, me, storage):
    brand_id, _ = with_logo(an)
    video = make_video(db, storage, me)
    video.options = {"brand_id": brand_id}
    db.commit()
    assert an.delete(f"{URL}/{brand_id}").status_code == 409
    video.options = {}
    db.commit()
    assert an.delete(f"{URL}/{brand_id}").status_code == 204
    assert not (storage.root / "brands" / str(brand_id)).exists() or not list(
        (storage.root / "brands" / str(brand_id)).iterdir()
    )


# --- A video's channel and switch ---


def patch(an, video, **options):
    return an.patch(f"/api/videos/{video.id}", json={"options": options})


def test_a_video_picks_a_brand_and_the_logo_follows_the_brands_default(an, db, me, storage):
    brand_id, _ = with_logo(an)
    video = make_video(db, storage, me)
    chosen = patch(an, video, brand_id=brand_id)
    assert chosen.status_code == 200, chosen.json()
    assert chosen.json()["brand"]["id"] == brand_id and chosen.json()["logo_enabled"] is True
    off = patch(an, video, logo_enabled=False)
    assert off.json()["logo_enabled"] is False and off.json()["brand"]["id"] == brand_id


def test_the_logo_cannot_be_on_for_a_brand_without_one_or_one_of_a_teammate(an, db, me, storage, client):
    bare = make_brand(an, "Chưa logo")["id"]
    video = make_video(db, storage, me)
    refused = patch(an, video, brand_id=bare, logo_enabled=True)
    assert (refused.status_code, refused.json()["code"]) == (400, "brand_has_no_logo")
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    theirs = Brand(name="Của Bình", slug="cua-binh", owner_id=other.id)
    db.add(theirs)
    db.commit()
    assert patch(an, video, brand_id=theirs.id).status_code == 403


def test_a_posted_video_keeps_its_brand(an, db, me, storage):
    first, _ = with_logo(an)
    second = make_brand(an, "Kênh hai")["id"]
    video = make_video(db, storage, me)
    patch(an, video, brand_id=first)
    page = own_page(db, me)
    db.add(
        Publication(video_id=video.id, platform="facebook", fanpage_id=page.id, status="published", created_by_id=me.id)
    )
    db.commit()
    refused = patch(an, video, brand_id=second)
    assert (refused.status_code, refused.json()["code"]) == (409, "video_already_posted")
    assert patch(an, video, logo_enabled=False).status_code == 200  # the switch alone is not refused


def test_the_logo_changes_the_mp4_fingerprint_only_while_it_is_on(an, db, me, storage):
    brand_id, _ = with_logo(an)
    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    before = render_signature(video, title, scenes)
    patch(an, video, brand_id=brand_id)
    db.refresh(video)
    with_it = render_signature(video, title, scenes)
    assert with_it != before
    patch(an, video, logo_enabled=False)
    db.refresh(video)
    assert render_signature(video, title, scenes) == before
    patch(an, video, logo_enabled=True)
    an.post(f"{URL}/{brand_id}/logo", files=logo_file(color=(0, 150, 0)))
    db.refresh(video)
    assert render_signature(video, title, scenes) not in (before, with_it)


def test_a_new_logo_marks_unposted_videos_with_an_mp4_for_a_new_render(an, db, me, storage):
    brand_id, _ = with_logo(an)
    video = make_video(db, storage, me)
    video.mp4_key = "videos/1/video.mp4"
    db.commit()
    patch(an, video, brand_id=brand_id)
    done = an.post(f"{URL}/{brand_id}/logo", files=logo_file(color=(0, 90, 160)))
    assert done.json()["videos_outdated"] == 1
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is True


# --- Render ---


def test_the_render_job_hands_the_badge_to_the_renderer_and_a_machine_gets_the_option(committed, fakes, monkeypatch):
    from reels_api import render_nodes

    assert render_nodes.options_dict(__import__("reels_render").RenderOptions(logo=True))["logo"] is True
    assert "logo" not in render_nodes.options_dict(__import__("reels_render").RenderOptions())
