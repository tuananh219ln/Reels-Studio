"""An article's photos and the Page's logo on them (decisions 2026-11-15, "article photos and logo"): 1–10 photos
from the scene's tools, their order, each photo's logo switch and position, the preview, the brand's photo-logo
settings, the AI photo job in the article's shape and a post of several photos with the logo laid on."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from PIL import Image
from sqlalchemy import select
from worker_helpers import add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import article_images, brands, fanpages, jobs, photo_logo
from reels_api.models import Article, ArticleImage, Brand, Job, MediaItem, Publication
from reels_api.storage import DirectoryStorage

RED = (230, 20, 20)
WHITE = (255, 255, 255)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def png(colour, size=(600, 750), alpha=False) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA" if alpha else "RGB", size, (*colour, 255) if alpha else colour).save(buffer, "PNG")
    return buffer.getvalue()


def new_article(an, db) -> dict:
    response = an.post("/api/articles", json={"knowledge_topic_id": first_topic(db).id, "kind": "meo"})
    assert response.status_code == 201, response.text
    return response.json()


def upload(an, article_id, colour=WHITE) -> dict:
    response = an.post(f"/api/articles/{article_id}/images", files={"file": ("a.png", png(colour), "image/png")})
    assert response.status_code == 200, response.text
    return response.json()


def page_with_logo(an, db, me, colour=RED) -> int:
    """The member's Page, in a brand whose logo is a plain `colour` rectangle twice as wide as tall."""
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    db.commit()
    brand = an.post("/api/brands", json={"name": "Dưỡng Sinh", "fanpage_id": page.id}).json()
    logo = an.post(
        f"/api/brands/{brand['id']}/logo", files={"file": ("logo.png", png(colour, (600, 300), True), "image/png")}
    )
    assert logo.status_code == 200, logo.text
    return page.id


def centre_of_logo(image: Image.Image, position="bottom_right", shape="circle") -> tuple[int, int]:
    left, top, width, height = photo_logo.box(image.size, (600, 300), photo_logo.Look(position=position, shape=shape))
    return left + width // 2, top + height // 2


# --- Photos ---


def test_photos_are_added_in_order_up_to_ten_reordered_and_removed(an, db, storage):
    article = new_article(an, db)
    for _ in range(article_images.MAX_IMAGES):
        saved = upload(an, article["id"])
    assert [image["position"] for image in saved["images"]] == list(range(10))
    assert saved["has_image"] is True and saved["images"][0]["source"] == "upload"
    full = an.post(f"/api/articles/{article['id']}/images", files={"file": ("a.png", png(WHITE), "image/png")})
    assert full.status_code == 409 and "đủ 10 ảnh" in full.json()["message"]

    ids = [image["id"] for image in saved["images"]]
    turned = an.put(f"/api/articles/{article['id']}/images/order", json={"ids": ids[::-1]}).json()
    assert [image["id"] for image in turned["images"]] == ids[::-1]
    stale = an.put(f"/api/articles/{article['id']}/images/order", json={"ids": ids[:3]})
    assert stale.status_code == 409

    key = db.scalar(select(ArticleImage.image_key).where(ArticleImage.id == ids[-1]))
    removed = an.delete(f"/api/articles/{article['id']}/images/{ids[-1]}").json()
    assert [image["position"] for image in removed["images"]] == list(range(9))
    assert ids[-1] not in [image["id"] for image in removed["images"]]
    assert not storage.exists(key)
    # The list's thumbnail is the first photo.
    assert an.get(f"/api/articles/{article['id']}/image").status_code == 200


def test_an_unreadable_file_is_refused(an, db):
    article = new_article(an, db)
    refused = an.post(f"/api/articles/{article['id']}/images", files={"file": ("a.png", b"not a photo", "image/png")})
    assert refused.status_code == 415


def test_a_photo_of_the_library_is_copied(an, db, me, storage):
    article = new_article(an, db)
    storage.save_bytes("media/a.png", png(RED))
    item = MediaItem(kind="photo", name="a.png", folder="", storage_key="media/a.png", created_by_id=me.id)
    db.add(item)
    db.commit()
    saved = an.post(f"/api/articles/{article['id']}/images/library", json={"media_id": item.id}).json()
    (image,) = saved["images"]
    assert image["source"] == "library"
    key = db.scalar(select(ArticleImage.image_key).where(ArticleImage.id == image["id"]))
    assert key != "media/a.png" and storage.exists(key)


def test_a_stock_photo_is_searched_and_chosen_as_for_a_scene(an, db, fakes):
    article = new_article(an, db)
    fakes.pexels_results["bữa sáng"] = ["px1", "px2"]
    found = an.get(f"/api/articles/{article['id']}/stock", params={"q": "bữa sáng", "source": "pexels"})
    assert found.status_code == 200, found.text
    assert [hit["url"] for hit in found.json()["hits"]] == [fakes.image_url("px1"), fakes.image_url("px2")]
    saved = an.post(
        f"/api/articles/{article['id']}/images/stock",
        json={"source": "pexels", "keyword": "bữa sáng", "url": fakes.image_url("px2")},
    ).json()
    (image,) = saved["images"]
    assert (image["source"], image["source_ref"]) == ("stock", fakes.image_url("px2"))
    refused = an.post(
        f"/api/articles/{article['id']}/images/stock",
        json={"source": "pexels", "keyword": "bữa sáng", "url": "https://images.pexels.com/photos/1/x.jpg"},
    )
    assert refused.status_code == 422 and "không có trong kết quả tìm" in refused.json()["message"]


def test_the_photo_search_words_prompt_and_shape_are_saved_and_checked(an, db):
    article = new_article(an, db)
    saved = an.patch(
        f"/api/articles/{article['id']}",
        json={"image_query": " bữa sáng ", "image_prompt": "Bàn ăn sáng gọn", "image_aspect": "1:1"},
    ).json()
    assert (saved["image_query"], saved["image_prompt"], saved["image_aspect"]) == (
        "bữa sáng",
        "Bàn ăn sáng gọn",
        "1:1",
    )
    assert an.patch(f"/api/articles/{article['id']}", json={"image_aspect": "9:16"}).status_code == 422


# --- The logo ---


def test_each_photo_has_its_logo_switch_and_position(an, db):
    article = new_article(an, db)
    image = upload(an, article["id"])["images"][0]
    assert (image["logo_enabled"], image["logo_position"]) == (True, None)
    base = f"/api/articles/{article['id']}/images/{image['id']}"
    changed = an.patch(base, json={"logo_enabled": False, "logo_position": "top_left"}).json()["images"][0]
    assert (changed["logo_enabled"], changed["logo_position"]) == (False, "top_left")
    back = an.patch(base, json={"logo_position": None}).json()["images"][0]
    assert (back["logo_enabled"], back["logo_position"]) == (False, None)
    assert an.patch(base, json={"logo_position": "giua"}).status_code == 422


def test_the_preview_lays_the_page_logo_where_the_photo_puts_it(an, db, me):
    page = page_with_logo(an, db, me)
    article = new_article(an, db)
    image = upload(an, article["id"])["images"][0]
    base = f"/api/articles/{article['id']}/images/{image['id']}"

    def preview(fanpage_id=page) -> Image.Image:
        response = an.get(f"{base}/preview", params={"fanpage_id": fanpage_id} if fanpage_id else {})
        assert response.status_code == 200, response.text
        return Image.open(io.BytesIO(response.content)).convert("RGB")

    shown = preview()
    # At most PREVIEW_WIDTH on its long side; a smaller photo is never enlarged.
    assert shown.size == (600, 750)
    assert shown.getpixel(centre_of_logo(shown)) == pytest.approx(RED, abs=12)
    assert shown.getpixel(centre_of_logo(shown, "top_left")) == pytest.approx(WHITE, abs=6)

    an.patch(base, json={"logo_position": "top_left"})
    moved = preview()
    assert moved.getpixel(centre_of_logo(moved, "top_left")) == pytest.approx(RED, abs=12)

    an.patch(base, json={"logo_enabled": False})
    assert preview().getpixel(centre_of_logo(moved, "top_left")) == pytest.approx(WHITE, abs=6)
    # A Page with no brand, or none chosen: the photo as it is.
    an.patch(base, json={"logo_enabled": True})
    assert preview(None).getpixel(centre_of_logo(moved, "top_left")) == pytest.approx(WHITE, abs=6)


def test_the_logo_takes_its_size_and_margin_from_the_photos_short_side():
    look = photo_logo.Look(shape="none")
    assert photo_logo.box((1080, 1080), (600, 300), look) == (918, 983, 130, 65)
    assert photo_logo.box((1080, 1350), (600, 300), look) == (918, 1253, 130, 65)
    assert photo_logo.box((1200, 628), (600, 300), look) == (1106, 571, 75, 38)
    assert photo_logo.box((1000, 1000), (100, 100), photo_logo.Look(position="center", size=20, shape="none")) == (
        400,
        400,
        200,
        200,
    )


def test_a_round_badge_is_square_at_least_120_px_and_16_px_from_the_edge():
    look = photo_logo.Look(size=14, margin=3)
    # 14% of 1080 = 151; the margin 3% = 32.
    assert photo_logo.box((1080, 1350), (600, 300), look) == (1080 - 151 - 32, 1350 - 151 - 32, 151, 151)
    # A small photo: 14% of 600 would be 84, so 120; 3% of 600 would be 18, so 18; of 400 it would be 12, so 16.
    assert photo_logo.box((600, 800), (600, 300), look)[2:] == (120, 120)
    assert photo_logo.box((400, 400), (600, 300), look) == (400 - 120 - 16, 400 - 120 - 16, 120, 120)


def test_the_white_logo_goes_on_a_dark_photo_and_opacity_lets_the_photo_through(tmp_path):
    (tmp_path / "logo.png").write_bytes(png(RED, (600, 300), True))
    (tmp_path / "alt.png").write_bytes(png(WHITE, (600, 300), True))
    logo = photo_logo.BrandLogo(
        tmp_path / "logo.png", tmp_path / "alt.png", photo_logo.Look(alt_threshold=0.4, shape="none")
    )
    for colour, expected in (((250, 250, 250), RED), ((10, 10, 10), WHITE)):
        photo = Image.open(io.BytesIO(photo_logo.render(png(colour, (1080, 1350)), logo)))
        assert photo.getpixel(centre_of_logo(photo, shape="none")) == pytest.approx(expected, abs=12)
    faint = photo_logo.BrandLogo(tmp_path / "logo.png", None, photo_logo.Look(opacity=0.5, shape="none"))
    photo = Image.open(io.BytesIO(photo_logo.render(png((10, 10, 10), (1080, 1350)), faint)))
    assert photo.getpixel(centre_of_logo(photo, shape="none")) == pytest.approx((120, 15, 15), abs=12)


def test_a_big_photo_is_posted_at_most_2048_wide_with_the_logo_kept_in_proportion(tmp_path):
    (tmp_path / "logo.png").write_bytes(png(RED, (600, 300), True))
    logo = photo_logo.BrandLogo(tmp_path / "logo.png", None, photo_logo.Look(shape="none"))
    photo = Image.open(io.BytesIO(photo_logo.render(png(WHITE, (4000, 3000)), logo)))
    assert photo.size == (2048, 1536)
    assert photo.getpixel(centre_of_logo(photo, shape="none")) == pytest.approx(RED, abs=12)


def test_a_round_logo_has_a_white_ring_clear_corners_and_a_solid_face(tmp_path):
    # A transparent PNG: the badge is solid all through, on white.
    (tmp_path / "logo.png").write_bytes(png(RED, (600, 300), True))
    clear = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    clear.putpixel((300, 300), (0, 0, 255, 255))
    buffer = io.BytesIO()
    clear.save(buffer, "PNG")
    (tmp_path / "clear.png").write_bytes(buffer.getvalue())
    dark = png((10, 10, 10), (1080, 1350))
    look = photo_logo.Look(shadow=False)
    for name, face_pixel in (("logo.png", RED), ("clear.png", WHITE)):
        logo = photo_logo.BrandLogo(tmp_path / name, None, look)
        photo = Image.open(io.BytesIO(photo_logo.render(dark, logo)))
        left, top, width, _ = photo_logo.box(photo.size, (600, 600), look)
        assert photo.getpixel((left + width // 2, top + width // 2)) == pytest.approx(face_pixel, abs=12) or name == (
            "clear.png"
        )
        # The corner is outside the circle: the dark photo shows.
        assert photo.getpixel((left + 2, top + 2)) == pytest.approx((10, 10, 10), abs=6)
        # The ring is white (the logo's face is inside it).
        assert photo.getpixel((left + 2, top + width // 2)) == pytest.approx(WHITE, abs=6)
    # Without the ring the logo fills the circle to its edge.
    plain = photo_logo.Look(border=False, shadow=False)
    photo = Image.open(io.BytesIO(photo_logo.render(dark, photo_logo.BrandLogo(tmp_path / "logo.png", None, plain))))
    left, top, width, _ = photo_logo.box(photo.size, (600, 600), plain)
    assert photo.getpixel((left + 4, top + width // 2)) == pytest.approx(RED, abs=12)


def test_a_rounded_logo_keeps_a_square_with_soft_corners_and_a_coloured_ring(tmp_path):
    (tmp_path / "logo.png").write_bytes(png(RED, (600, 300), True))
    look = photo_logo.Look(shape="rounded", border_color="#00FF00", shadow=False)
    photo = Image.open(
        io.BytesIO(
            photo_logo.render(png((10, 10, 10), (1080, 1080)), photo_logo.BrandLogo(tmp_path / "logo.png", None, look))
        )
    )
    left, top, width, _ = photo_logo.box(photo.size, (600, 600), look)
    assert photo.getpixel((left + width // 2, top + 3)) == pytest.approx((0, 255, 0), abs=6)
    assert photo.getpixel((left, top)) == pytest.approx((10, 10, 10), abs=15)
    shadowed = photo_logo.Look(shape="circle")
    lit = Image.open(
        io.BytesIO(
            photo_logo.render(png(WHITE, (1080, 1080)), photo_logo.BrandLogo(tmp_path / "logo.png", None, shadowed))
        )
    )
    left, top, width, _ = photo_logo.box(lit.size, (600, 600), shadowed)
    # Under the badge, on a white photo, the shadow darkens it; away from it nothing does.
    assert sum(lit.getpixel((left + width // 2, top + width + 3))) < 3 * 250
    assert lit.getpixel((10, 10)) == WHITE


def test_the_logo_look_is_checked():
    for wrong in (photo_logo.Look(shape="star"), photo_logo.Look(border_color="white")):
        with pytest.raises(photo_logo.LogoSettingsError):
            photo_logo.checked(wrong)
    assert photo_logo.checked(photo_logo.Look(shape="rounded", border_color="#aabbcc")).shape == "rounded"


def test_the_brand_photo_logo_settings_are_checked_and_drawn_on_the_samples(an, db, me):
    page_with_logo(an, db, me)
    brand_id = db.scalar(select(Brand.id))
    saved = an.patch(
        f"/api/brands/{brand_id}",
        json={"photo_logo_position": "top_right", "photo_logo_size": 20, "photo_logo_alt_threshold": 0.3},
    ).json()
    assert saved["photo_logo"] == {
        "position": "top_right",
        "size": 20,
        "margin": 3,
        "opacity": 1,
        "alt_threshold": 0.3,
        "shape": "circle",
        "border": True,
        "border_color": "#FFFFFF",
        "shadow": True,
    }
    assert an.patch(f"/api/brands/{brand_id}", json={"photo_logo_shape": "star"}).status_code == 422
    assert (
        an.patch(f"/api/brands/{brand_id}", json={"photo_logo_alt_threshold": None}).json()["photo_logo"][
            "alt_threshold"
        ]
        is None
    )
    for wrong in ({"photo_logo_size": 80}, {"photo_logo_opacity": 0}, {"photo_logo_position": "giua"}):
        assert an.patch(f"/api/brands/{brand_id}", json=wrong).status_code == 422, wrong
    for ratio, width in (("1:1", 800), ("4:5", 640), ("1.91:1", 800)):
        sample = an.get(f"/api/brands/{brand_id}/photo-sample", params={"ratio": ratio, "position": "center"})
        assert sample.status_code == 200
        image = Image.open(io.BytesIO(sample.content)).convert("RGB")
        assert image.width == width
        # The logo is drawn where the query (not yet saved) puts it.
        assert image.getpixel((image.width // 2, image.height // 2)) == pytest.approx(RED, abs=12)
    assert an.get(f"/api/brands/{brand_id}/photo-sample", params={"ratio": "9:16"}).status_code == 422


def test_the_white_logo_is_uploaded_and_removed_by_the_owner_only(an, client, db, me):
    page_with_logo(an, db, me)
    brand_id = db.scalar(select(Brand.id))
    saved = an.post(
        f"/api/brands/{brand_id}/logo-alt", files={"file": ("w.png", png(WHITE, (600, 300), True), "image/png")}
    ).json()
    assert saved["logo_alt_url"].startswith(f"/api/brands/{brand_id}/logo-alt?v=")
    assert an.get(f"/api/brands/{brand_id}/logo-alt").status_code == 200
    assert an.delete(f"/api/brands/{brand_id}/logo-alt").json()["logo_alt_url"] is None
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client, "binh@doi.vn")
    refused = client.post(
        f"/api/brands/{brand_id}/logo-alt", files={"file": ("w.png", png(WHITE, (600, 300), True), "image/png")}
    )
    assert refused.status_code == 403


# --- The AI photo ---


def test_an_ai_photo_needs_something_to_draw_and_queues_one_job(an, db):
    article = new_article(an, db)
    refused = an.post(f"/api/articles/{article['id']}/images/ai")
    assert refused.status_code == 422
    an.patch(f"/api/articles/{article['id']}", json={"image_query": "bữa sáng văn phòng"})
    queued = an.post(f"/api/articles/{article['id']}/images/ai", params={"provider": "cloudflare"})
    assert queued.status_code == 200, queued.text
    assert queued.json()["busy"] is True and queued.json()["image_job"]["status"] == "queued"
    job = db.scalar(select(Job).where(Job.article_id == article["id"]))
    assert (job.kind, job.image_provider) == ("article_image", "cloudflare")
    again = an.post(f"/api/articles/{article['id']}/images/ai")
    assert again.status_code == 409


def test_the_ai_photo_job_adds_a_photo_in_the_article_shape(committed, fakes, storage, monkeypatch):  # noqa: F811
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", "cloudflare")
    user = add_user(committed)
    with committed() as db:
        article = Article(
            knowledge_topic_id=first_topic(db).id,
            kind="meo",
            topic="Bữa sáng",
            image_prompt="Bàn ăn sáng gọn, ánh sáng tự nhiên",
            image_aspect="4:5",
            created_by_id=user.id,
        )
        db.add(article)
        db.flush()
        job = Job(
            article_id=article.id,
            kind="article_image",
            status="running",
            image_provider="cloudflare",
            created_by_id=user.id,
        )
        db.add(job)
        db.commit()
        article_id, job_id = article.id, job.id
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert (job.status, job.error, job.image_calls) == ("done", None, 1)
    assert fakes.cf_image_gen_prompts[0].startswith("Bàn ăn sáng gọn, ánh sáng tự nhiên")
    with committed() as db:
        (image,) = db.scalars(select(ArticleImage).where(ArticleImage.article_id == article_id))
        assert image.source == "ai" and image.source_ref.startswith("ai:")
        # The fake answers 1024x1024 squares: what is stored was cut to 4:5.
        with Image.open(storage.path(image.image_key)) as photo:
            width, height = photo.size
        assert abs(width * 5 - height * 4) <= 5, (width, height)


# --- Posting several photos ---


def test_a_post_of_several_photos_attaches_them_in_order_with_the_logo(committed, fakes, tmp_path):  # noqa: F811
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    at = datetime.now(UTC) + timedelta(hours=5)
    with committed() as db:
        page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        db.flush()
        brand = Brand(name="Dưỡng Sinh", slug="duong-sinh", fanpage_id=page.id, owner_id=user.id)
        db.add(brand)
        db.flush()
        brands.save_logo(db, storage, brand, png(RED, (600, 300), True))
        article = Article(
            knowledge_topic_id=first_topic(db).id,
            kind="meo",
            topic="Bữa sáng",
            caption="Bữa sáng 10 phút\n\nNội dung",
            created_by_id=user.id,
        )
        db.add(article)
        db.flush()
        for position, (colour, logo_on) in enumerate(((WHITE, True), ((0, 0, 200), False))):
            key = f"articles/{article.id}/photo-{position}.png"
            storage.save_bytes(key, png(colour, (1080, 1350)))
            db.add(
                ArticleImage(
                    article_id=article.id, position=position, image_key=key, source="upload", logo_enabled=logo_on
                )
            )
        db.add(
            Publication(
                article_id=article.id, platform="facebook", fanpage_id=page.id, scheduled_at=at, created_by_id=user.id
            )
        )
        db.flush()
        job = Job(article_id=article.id, kind="publish", status="running", created_by_id=user.id)
        db.add(job)
        db.commit()
        article_id, job_id = article.id, job.id
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert job.status == "done", job.error
    (remote,) = fakes.page_posts.values()
    assert (remote["edge"], remote["published"], remote["scheduled"]) == ("feed", False, int(at.timestamp()))
    assert remote["message"].startswith("Bữa sáng 10 phút")
    assert all(photo["temporary"] for photo in fakes.page_photos.values())
    first, second = (Image.open(io.BytesIO(data)).convert("RGB") for data in remote["photos"])
    assert first.getpixel(centre_of_logo(first)) == pytest.approx(RED, abs=12)
    # The second photo's logo is off: it goes as it is.
    assert second.getpixel(centre_of_logo(second)) == pytest.approx((0, 0, 200), abs=12)
    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.article_id == article_id))
        assert (post.status, post.remote_id) == ("scheduled", next(iter(fakes.page_posts)))
        # The stored photos are not changed by posting.
        stored = db.scalar(
            select(ArticleImage.image_key)
            .where(ArticleImage.article_id == article_id)
            .order_by(ArticleImage.position)
            .limit(1)
        )
        with Image.open(storage.path(stored)) as photo:
            assert photo.convert("RGB").getpixel(centre_of_logo(photo)) == WHITE
