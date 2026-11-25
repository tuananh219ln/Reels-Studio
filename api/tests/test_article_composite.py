"""The article's "Ảnh ghép chữ + ảnh" (article_composite.py): the render, the auto mode, the line split, and the
routes that make, reopen and preview it."""

import io

import pytest
from conftest import first_topic, login, make_user
from PIL import Image

from reels_api import article_composite as composite
from reels_api.models import ArticleImage
from reels_api.storage import DirectoryStorage

HOOK = ["Hay mệt mỏi, hoa mắt?", "Thêm cải bó xôi", "vào bữa ăn mỗi ngày 👇"]
TAG = "NGÀY 5 · THỰC PHẨM TỐT CHO SỨC KHỎE"


def photo(width, height, colour="#2a8f3c") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, "JPEG")
    return buffer.getvalue()


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def run(width, height, **more):
    return composite.render(photo(width, height), composite.Options(HOOK, TAG, **more))


# --- The render ---


def test_the_output_is_4_by_5_with_a_band_of_450_px_and_no_white_edge():
    result = run(1200, 1200, mode="cover")
    image = opened(result.data)
    assert image.size == (1080, 1350)
    # Under the band is the photo itself, edge to edge.
    for x, y in ((0, 450), (1079, 450), (0, 1349), (1079, 1349), (540, 900)):
        assert image.getpixel((x, y)) == pytest.approx((0x2A, 0x8F, 0x3C), abs=8)
    # The band is the gradient: its first row is the first stop, its last row the last.
    assert image.getpixel((2, 0)) == pytest.approx((0xFF, 0xC8, 0x57), abs=6)
    assert image.getpixel((2, 449)) == pytest.approx((0xE8, 0x43, 0x2E), abs=6)


def test_the_font_fits_the_spec_example_and_the_text_is_centred():
    result = run(1200, 1200)
    assert 60 <= result.font_size <= 68
    top, block, _ = composite.block_layout(HOOK, TAG, result.font_size)
    assert abs(top - (450 - (top + block))) <= 2
    # Under the pill and the lines the band is still the gradient: the first white pixel is not above the block.
    band = opened(result.data).crop((0, 0, 1080, 450))
    ink = [y for y in range(450) if any(min(band.getpixel((x, y))) > 235 for x in range(0, 1080, 2))]
    assert ink[0] >= top - 2 and ink[-1] <= top + block + 2


def test_the_longest_line_stays_within_86_percent_of_the_width():
    lines = ["Một dòng tiêu đề rất rất dài để thử", "ngắn", "ngắn"]
    size = composite.fit_font(lines, True)
    assert max(composite._font(size).getlength(line) for line in lines) <= 1080 * 0.86
    assert composite.render(photo(1200, 1200), composite.Options(lines, TAG)).font_size == size


def test_vietnamese_marks_are_drawn_and_emoji_are_dropped_before_measuring():
    assert composite.strip_emoji("vào bữa ăn mỗi ngày 👇") == "vào bữa ăn mỗi ngày"
    assert composite.strip_emoji("ệ ỏ ắ ữ") == "ệ ỏ ắ ữ"
    with_emoji = composite.render(photo(1200, 1200), composite.Options(HOOK, TAG))
    without = composite.render(photo(1200, 1200), composite.Options([*HOOK[:2], "vào bữa ăn mỗi ngày"], TAG))
    assert with_emoji.data == without.data


def test_the_same_options_give_the_same_bytes():
    assert run(1920, 1080).data == run(1920, 1080).data


@pytest.mark.parametrize(
    ("size", "expected"),
    [((1200, 1200), "cover"), ((1600, 1200), "cover"), ((1920, 1080), "cover"),
     ((2520, 1080), "blur"), ((1080, 1350), "blur"), ((1080, 1920), "blur"), ((566, 471), "blur")],
)  # fmt: skip
def test_auto_mode_follows_the_spec_table(size, expected):
    assert composite.choose_mode(*size) == expected
    assert run(*size).mode_used == expected


def test_a_mode_chosen_by_the_member_wins_over_auto():
    assert run(1200, 1200, mode="blur").mode_used == "blur"
    assert run(1080, 1920, mode="cover").mode_used == "cover"


def test_blur_mode_shows_the_whole_photo_on_a_dimmed_blur():
    buffer = io.BytesIO()
    tall = Image.new("RGB", (900, 1200), "#ffffff")
    tall.paste("#ff0000", (0, 0, 900, 40))  # a red strip on the photo's top edge
    tall.save(buffer, "JPEG", quality=95)
    result = composite.render(buffer.getvalue(), composite.Options(HOOK, None, mode="blur"))
    image = opened(result.data)
    # The picture is scaled to 675 x 900 and centred: its red top edge is at y 450, between x 202 and 877.
    assert image.getpixel((540, 453))[0] > 200 and image.getpixel((540, 453))[1] < 60
    # Left of the picture is the blur, dimmed to 75%: no white, no band-coloured edge.
    left = image.getpixel((20, 900))
    assert max(left) <= 0.75 * 255 + 8


def test_cover_focus_moves_the_crop():
    wide = Image.new("RGB", (2000, 1000), "#0000ff")
    wide.paste("#ff0000", (0, 0, 400, 1000))  # red on the left fifth
    buffer = io.BytesIO()
    wide.save(buffer, "PNG")
    left = composite.render(buffer.getvalue(), composite.Options(["Món"], None, mode="cover", focus_x=0))
    right = composite.render(buffer.getvalue(), composite.Options(["Món"], None, mode="cover", focus_x=1))
    assert opened(left.data).getpixel((20, 900))[0] > 200
    assert opened(right.data).getpixel((20, 900))[2] > 200


def test_warnings_name_a_small_photo_a_blown_up_one_and_a_tiny_font():
    small = composite.render(photo(566, 471), composite.Options(HOOK, TAG))
    assert {warning["code"] for warning in small.warnings} == {"LOW_RES_SOURCE", "UPSCALED"}
    long_line = ["Một dòng rất rất rất rất rất rất rất rất rất dài", "hai", "ba"]
    tiny = composite.render(photo(1200, 1200), composite.Options(long_line, TAG))
    assert "FONT_TOO_SMALL" in {warning["code"] for warning in tiny.warnings} and tiny.font_size < 48
    assert run(1200, 1200).warnings == []


def test_bad_options_are_refused_with_the_spec_codes():
    for options, code in (
        (composite.Options(["a", "b", "c", "d"]), "TITLE_TOO_LONG"),
        (composite.Options([]), "TITLE_EMPTY"),
        (composite.Options(["a"], preset="tim"), "INVALID_PRESET"),
        (composite.Options(["a"], mode="x"), "INVALID_MODE"),
        (composite.Options(["a"], focus_x=2), "INVALID_FOCUS"),
    ):
        with pytest.raises(composite.CompositeError) as err:
            composite.render(photo(100, 100), options)
        assert err.value.code == code
    with pytest.raises(composite.CompositeError) as err:
        composite.render(b"not a picture", composite.Options(["a"]))
    assert err.value.code == "SOURCE_UNREADABLE"


# --- Splitting the caption's first line (spec §7) ---


def test_a_short_title_stays_one_line_and_a_long_one_is_split_evenly():
    assert composite.split_title("Ăn sáng muộn có sao?", False) == ["Ăn sáng muộn có sao?"]
    lines = composite.split_title("Hay mệt mỏi, hoa mắt? Thêm cải bó xôi vào bữa ăn mỗi ngày", False)
    assert lines == ["Hay mệt mỏi, hoa mắt?", "Thêm cải bó xôi vào", "bữa ăn mỗi ngày"] or len(lines) in (2, 3)
    assert all(len(line) <= 24 for line in lines) and " ".join(lines).startswith("Hay mệt mỏi")


def test_the_day_prefix_goes_only_when_there_is_a_tag():
    assert composite.split_title("Ngày 5 | Cải bó xôi tốt sao?", True) == ["Cải bó xôi tốt sao?"]
    assert composite.split_title("Ngày 5 | Cải bó xôi", False) == ["Ngày 5 | Cải bó xôi"]


def test_a_break_after_a_question_mark_is_preferred():
    assert composite.split_title("Mệt mỏi hoa mắt? Cải bó xôi giúp bạn", False)[0] == "Mệt mỏi hoa mắt?"


def test_a_title_that_does_not_fit_three_lines_is_an_error_not_cut():
    with pytest.raises(composite.CompositeError) as err:
        composite.split_title("từ " * 40, False)
    assert err.value.code == "TITLE_TOO_LONG"


# --- Routes ---


@pytest.fixture
def an(client, db):
    make_user(db)
    login(client)
    return client


@pytest.fixture
def article(an, db):
    made = an.post(
        "/api/articles", json={"knowledge_topic_id": first_topic(db).id, "kind": "kien_thuc", "topic": "Cải bó xôi"}
    ).json()
    an.patch(f"/api/articles/{made['id']}", json={"caption": "Hay mệt mỏi, hoa mắt?\n\nNội dung"})
    return made["id"]


def upload(an, article, data=None):
    files = {"file": ("mon.jpg", data or photo(1200, 1200), "image/jpeg")}
    return an.post(f"/api/articles/{article}/images", files=files).json()["images"][-1]


def test_a_composite_replaces_the_text_card_and_the_source_photo_and_takes_the_first_place(an, article, db, tmp_path):
    an.post(f"/api/articles/{article}/images/text-card", json={"preset": "cam"})
    dish = upload(an, article)
    other = upload(an, article, photo(800, 800, "#aa0000"))
    storage = DirectoryStorage(tmp_path / "storage")
    old_keys = [row.image_key for row in db.query(ArticleImage).filter_by(article_id=article).all()]

    made = an.post(
        f"/api/articles/{article}/images/composite", json={"image_id": dish["id"], "lines": HOOK, "tag": TAG}
    ).json()
    assert [(image["source"], image["source_label"]) for image in made["images"][:1]] == [("composite", "Ảnh ghép")]
    assert [image["position"] for image in made["images"]] == [0, 1]
    assert made["images"][1]["id"] == other["id"]
    result = made["composite_result"]
    assert result["mode_used"] == "cover" and 60 <= result["font_size"] <= 68
    assert [warning["code"] for warning in result["warnings"]] == ["EXTRA_IMAGES"]
    assert made["images"][0]["composite"]["lines"] == HOOK
    assert all(not storage.exists(key) for key in old_keys[:2])  # the text card and the source photo are gone
    assert opened(an.get(f"/api/articles/{article}/image").content).size == (1080, 1350)


def test_a_composite_without_lines_takes_the_caption_and_the_plan_tag_is_optional(an, article):
    dish = upload(an, article)
    made = an.post(f"/api/articles/{article}/images/composite", json={"image_id": dish["id"]}).json()
    assert made["images"][0]["composite"]["lines"] == ["Hay mệt mỏi, hoa mắt?"]
    assert made["images"][0]["composite"]["tag"] is None
    assert made["composite_result"]["warnings"] == []


def test_exactly_one_source_is_needed_and_an_overlong_title_is_refused(an, article):
    dish = upload(an, article)
    assert an.post(f"/api/articles/{article}/images/composite", json={}).status_code == 422
    both = {"image_id": dish["id"], "media_id": 1}
    assert an.post(f"/api/articles/{article}/images/composite", json=both).status_code == 422
    refused = an.post(
        f"/api/articles/{article}/images/composite", json={"image_id": dish["id"], "lines": ["a", "b", "c", "d"]}
    )
    assert refused.status_code == 422 and refused.json()["code"] == "title_too_long"
    assert len(an.get(f"/api/articles/{article}").json()["images"]) == 1  # nothing was removed or added


def test_a_composite_is_reopened_and_drawn_again_from_its_kept_photo(an, article, db, tmp_path):
    dish = upload(an, article)
    made = an.post(f"/api/articles/{article}/images/composite", json={"image_id": dish["id"], "lines": HOOK}).json()
    image = made["images"][0]
    row = db.get(ArticleImage, image["id"])
    old_key = row.image_key
    assert an.get(image["composite"]["source_url"]).status_code == 200
    edited = an.put(
        f"/api/articles/{article}/images/{image['id']}/composite",
        json={"lines": ["Món mới"], "tag": "NGÀY 6", "preset": "xanh_la", "mode": "blur"},
    ).json()
    assert edited["composite_result"]["mode_used"] == "blur"
    assert edited["images"][0]["composite"] | {"source_url": ""} == {
        "lines": ["Món mới"], "tag": "NGÀY 6", "preset": "xanh_la", "mode": "blur",
        "focus_x": 0.5, "focus_y": 0.5, "source_url": "",
    }  # fmt: skip
    db.expire_all()
    assert db.get(ArticleImage, image["id"]).image_key != old_key
    assert not DirectoryStorage(tmp_path / "storage").exists(old_key)
    plain = upload(an, article)
    assert an.put(f"/api/articles/{article}/images/{plain['id']}/composite", json={"lines": ["a"]}).status_code == 422


def test_the_preview_draws_without_saving(an, article):
    dish = upload(an, article)
    response = an.post(
        f"/api/articles/{article}/images/composite/preview",
        json={"image_id": dish["id"], "lines": HOOK, "tag": TAG, "mode": "blur"},
    )
    assert response.status_code == 200 and response.headers["x-composite-mode"] == "blur"
    assert opened(response.content).size == (1080, 1350)
    assert len(an.get(f"/api/articles/{article}").json()["images"]) == 1
    assert (
        an.post(f"/api/articles/{article}/images/composite/preview", json={"url": "https://anh.vn/a.jpg"}).status_code
        == 422
    )


def test_removing_a_composite_removes_its_kept_photo_too(an, article, db, tmp_path):
    dish = upload(an, article)
    made = an.post(f"/api/articles/{article}/images/composite", json={"image_id": dish["id"], "lines": HOOK}).json()
    row = db.get(ArticleImage, made["images"][0]["id"])
    keys = [row.image_key, row.opts["source_key"]]
    storage = DirectoryStorage(tmp_path / "storage")
    assert all(storage.exists(key) for key in keys)
    an.delete(f"/api/articles/{article}/images/{row.id}")
    assert not any(storage.exists(key) for key in keys)
