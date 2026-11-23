import random
from pathlib import Path

import pytest
from conftest import scene, write_script
from PIL import Image, ImageFilter, ImageStat

from reels_render.errors import InputError
from reels_render.framing import (
    COVER,
    GAP,
    SQUARE,
    WHOLE,
    choose_kind,
    compose,
    frame_photo,
    is_blurry,
    padded_band,
    plan_frame,
    strip_padding,
)
from reels_render.images import fit_image
from reels_render.script import load_script
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH, SAFE_ZONE

TEXT = 300


def noisy(size: tuple[int, int], seed: int = 1) -> Image.Image:
    """A photo-like picture: every pixel different, so it is sharp everywhere."""
    rng = random.Random(seed)
    return Image.frombytes("RGB", size, bytes(rng.randrange(40, 220) for _ in range(size[0] * size[1] * 3)))


@pytest.mark.parametrize(
    ("size", "kind"),
    [
        ((1920, 1080), WHOLE),  # 16:9 keeps its shape
        ((1380, 1000), SQUARE),  # 1.38: cut square like a 5:4 photo, so the two scenes match
        ((1600, 1000), SQUARE),  # 16:10, the widest cut square
        ((1620, 1000), WHOLE),
        ((1080, 860), SQUARE),  # 5:4, the pomelo scene
        ((1000, 1000), SQUARE),
        ((900, 1200), SQUARE),  # 3:4
        ((1080, 1350), SQUARE),  # 4:5
        ((1000, 1500), COVER),  # 2:3
        ((1080, 1920), COVER),
    ],
)
def test_auto_chooses_by_the_photos_shape(size, kind):
    assert choose_kind(*size, "auto") == kind


@pytest.mark.parametrize("fit", [COVER, WHOLE, SQUARE])
def test_a_forced_fit_is_kept_whatever_the_shape(fit):
    assert choose_kind(1920, 1080, fit) == fit and choose_kind(1080, 1920, fit) == fit


def test_square_text_on_top_then_the_photo_right_under_it():
    framing = plan_frame(1080, 860, "auto", TEXT)
    top = SAFE_ZONE[1]
    assert framing.kind == SQUARE
    assert framing.picture == (0, top + TEXT + GAP, FRAME_WIDTH, FRAME_WIDTH)
    assert framing.text_centre == (FRAME_WIDTH // 2, top + TEXT // 2)
    # The square is the photo's full height from the middle.
    assert framing.crop == (110, 0, 970, 860)


def test_text_placed_low_puts_the_photo_above_it():
    framing = plan_frame(1080, 860, "auto", TEXT, centre=(540, 1300))
    bottom = SAFE_ZONE[3]
    assert framing.picture == (0, bottom - TEXT - GAP - FRAME_WIDTH, FRAME_WIDTH, FRAME_WIDTH)
    assert framing.text_centre == (FRAME_WIDTH // 2, bottom - TEXT + TEXT // 2)


def test_every_square_scene_of_a_video_lands_at_the_same_place():
    shapes = [(1080, 860), (1200, 900), (800, 1000), (500, 500)]
    assert len({plan_frame(*shape, "auto", TEXT).picture for shape in shapes}) == 1


def test_logo_row_pushes_the_text_and_photo_down():
    framing = plan_frame(1080, 860, "auto", TEXT, min_top=370)
    assert framing.text_centre == (540, 370 + TEXT // 2)
    assert framing.picture[1] == 370 + TEXT + GAP


def test_crop_offset_slides_the_square_along_the_longer_side():
    assert plan_frame(1080, 860, SQUARE, TEXT, crop_offset=0).crop == (0, 0, 860, 860)
    assert plan_frame(1080, 860, SQUARE, TEXT, crop_offset=1).crop == (220, 0, 1080, 860)
    assert plan_frame(800, 1000, SQUARE, TEXT, crop_offset=1).crop == (0, 200, 800, 1000)


def test_wide_photo_and_text_are_centred_together_in_the_safe_zone():
    framing = plan_frame(1920, 1080, "auto", TEXT)
    x, y, width, height = framing.picture
    assert (x, width, height) == (0, FRAME_WIDTH, 608)
    text_top = framing.text_centre[1] - TEXT // 2
    assert text_top + TEXT + GAP == y
    # Equal room above the text and below the photo, inside the safe zone.
    assert abs((text_top - SAFE_ZONE[1]) - (SAFE_ZONE[3] - (y + height))) <= 1


def test_no_text_centres_the_photo_and_leaves_the_box_alone():
    framing = plan_frame(1080, 860, "auto", 0)
    assert framing.picture == (0, (FRAME_HEIGHT - FRAME_WIDTH) // 2, FRAME_WIDTH, FRAME_WIDTH)
    assert framing.text_centre is None


def test_a_photo_that_fills_the_frame_keeps_its_text_on_the_same_line_as_the_framed_ones():
    """9:16 under "Tự động": the text goes on the top line, centred in the same block, not at the template's place."""
    framing = plan_frame(1080, 1920, "auto", TEXT)
    assert framing.kind == COVER and framing.picture is None
    assert framing.text_centre == plan_frame(1080, 860, "auto", TEXT).text_centre
    below = plan_frame(1080, 1920, "auto", TEXT, centre=(540, 1300))
    assert below.text_centre == plan_frame(1080, 860, "auto", TEXT, centre=(540, 1300)).text_centre


def test_a_forced_cover_keeps_the_template_place():
    framing = plan_frame(1080, 1920, COVER, TEXT)
    assert framing.kind == COVER and framing.picture is None and framing.text_centre is None


def test_with_a_reserve_every_photo_starts_on_one_line_and_the_text_is_centred_in_its_block():
    """The video's tallest text box (`reserve`) decides the line: a short text, a tall one and no text all put their
    photo at the same row, and the text keeps the block's middle."""
    reserve = 300
    shapes = [(1080, 860), (1380, 1000), (900, 1200), (1920, 1080)]
    frames = [plan_frame(*shape, "auto", text, reserve=reserve) for shape in shapes for text in (96, 200, 300, 0)]
    assert len({frame.picture[1] for frame in frames}) == 1
    assert {frame.text_centre[1] for frame in frames if frame.text_centre} == {SAFE_ZONE[1] + reserve // 2}
    assert plan_frame(1080, 860, "auto", 0, reserve=reserve).text_centre is None
    # Photos of every shape start the same row, though a wide one is shorter.
    assert (
        plan_frame(1920, 1080, "auto", 96, reserve=reserve).picture[3]
        < plan_frame(1080, 860, "auto", 96, reserve=reserve).picture[3]
    )


def test_with_a_reserve_text_placed_low_gets_its_block_at_the_bottom_and_the_photo_above_it():
    low = (540, 1300)
    bottom = SAFE_ZONE[3]
    short = plan_frame(1080, 860, "auto", 100, centre=low, reserve=300)
    tall = plan_frame(1080, 860, "auto", 300, centre=low, reserve=300)
    assert short.picture == tall.picture == (0, bottom - 300 - GAP - FRAME_WIDTH, FRAME_WIDTH, FRAME_WIDTH)
    assert short.text_centre == tall.text_centre == (540, bottom - 150)


def test_the_logo_row_moves_the_whole_shared_block_down():
    framing = plan_frame(1080, 860, "auto", 200, min_top=370, reserve=300)
    assert framing.picture[1] == 370 + 300 + GAP and framing.text_centre == (540, 370 + 150)


def test_tall_photo_forced_whole_fits_the_height():
    framing = plan_frame(500, 1500, WHOLE, TEXT)
    # Laid at the frame's full height with the blurred copy at its sides, never past the frame.
    assert framing.picture == ((FRAME_WIDTH - 640) // 2, 0, 640, FRAME_HEIGHT)


def test_compose_lays_the_photo_sharp_over_a_darker_blurred_copy():
    photo = Image.new("RGB", (600, 480), (240, 200, 40))
    photo.paste((30, 160, 60), (0, 0, 600, 240))  # green top half, yellow bottom half
    framing = plan_frame(*photo.size, "auto", TEXT)
    frame = compose(photo, framing)
    assert frame.size == (FRAME_WIDTH, FRAME_HEIGHT)
    x, y, width, height = framing.picture
    # The photo is all there, sharp: the green half above, the yellow half below.
    assert frame.getpixel((540, y + 40))[1] > 140 and frame.getpixel((540, y + height - 40))[0] > 220
    # Above it, the blurred and darkened copy: no black bars, darker than the photo.
    above = frame.getpixel((540, y // 2))
    assert sum(above) > 60 and sum(above) < sum(frame.getpixel((540, y + 40)))


def test_a_padded_frame_gives_back_its_real_band():
    real = noisy((1080, 860))
    padded, framing = frame_photo(real, WHOLE, 0)
    top = framing.picture[1]
    band = padded_band(padded)
    assert band is not None
    assert abs(band[0] - top) <= 12 and abs(band[1] - (top + 860)) <= 24
    assert strip_padding(padded).size[1] == band[1] - band[0]


@pytest.mark.parametrize(
    "picture",
    [
        noisy((540, 960)),  # a 9:16 photo sharp all over
        noisy((960, 540)),  # not 9:16 at all
        noisy((540, 960)).filter(ImageFilter.GaussianBlur(20)),  # soft all over
    ],
)
def test_other_photos_are_not_taken_for_padded_frames(picture):
    assert padded_band(picture) is None
    assert strip_padding(picture) is picture


def test_fit_image_writes_the_copy_and_the_photo_and_says_where_the_text_goes(tmp_path):
    source = tmp_path / "pomelo.jpg"
    noisy((540, 430)).save(source)
    target = tmp_path / "scene.jpg"
    fitted = fit_image(source, target, "Cảnh 1", "auto", TEXT, None, None)
    assert fitted.text_centre == (540, SAFE_ZONE[1] + TEXT // 2)
    assert fitted.box == (0, SAFE_ZONE[1] + TEXT + GAP, FRAME_WIDTH, FRAME_WIDTH)
    with Image.open(target) as copy, Image.open(fitted.picture) as photo:
        assert copy.size == (FRAME_WIDTH, FRAME_HEIGHT)
        assert photo.size == (FRAME_WIDTH, FRAME_WIDTH)
        # The copy is blurred: where the photo goes it is much smoother than the photo itself.
        under = copy.crop((0, fitted.box[1], FRAME_WIDTH, fitted.box[1] + FRAME_WIDTH))
        assert (
            ImageStat.Stat(under.filter(ImageFilter.FIND_EDGES)).mean[0]
            < 0.2 * ImageStat.Stat(photo.filter(ImageFilter.FIND_EDGES)).mean[0]
        )


def test_framed_boxes_are_even_for_the_mp4s_colour_planes():
    for size in [(1000, 800), (1921, 1080), (501, 1500), (777, 333)]:
        for centre in (None, (540, 1300)):
            for text in (0, 301, 299):
                framing = plan_frame(*size, "auto" if size != (501, 1500) else WHOLE, text, centre)
                assert all(value % 2 == 0 for value in framing.picture), (size, centre, text, framing.picture)


def test_cover_fit_image_is_the_photo_as_before(tmp_path):
    source = tmp_path / "wide.jpg"
    noisy((400, 300)).save(source)
    target = tmp_path / "scene.jpg"
    fitted = fit_image(source, target, "Cảnh 1", COVER, TEXT, None, None)
    assert fitted.text_centre is None and fitted.picture is None
    with Image.open(target) as written:
        assert written.size == (400, 300)
        assert ImageStat.Stat(written).stddev[0] > 20


def test_script_reads_the_fit_and_its_offset(tmp_path):
    noisy((40, 40)).save(tmp_path / "a.jpg")
    script = load_script(
        write_script(tmp_path, {"title": scene(), "scenes": [scene(image_fit="square", image_crop_offset=0.2)]})
    )
    assert script.title.image_fit == COVER and script.title.image_crop_offset is None
    assert script.scenes[0].image_fit == SQUARE and script.scenes[0].image_crop_offset == 0.2
    for bad in ({"image_fit": "stretch"}, {"image_crop_offset": 2}, {"image_crop_offset": "a"}):
        with pytest.raises(InputError, match="image_"):
            load_script(write_script(tmp_path, {"title": scene(), "scenes": [scene(**bad)]}))


SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "xuong-khop"


@pytest.mark.parametrize("name", ["02-sua-chua.jpg", "03-dau-phu.jpg", "05-vung-den.jpg"])
def test_a_sharp_photo_is_not_blurry_but_its_blurred_copy_is(name):
    """White tofu on a white board has little texture, yet is sharp for its contrast: it must not warn."""
    photo = Image.open(SAMPLES / name).convert("RGB")
    assert not is_blurry(photo)
    assert is_blurry(photo.filter(ImageFilter.GaussianBlur(3)))


def test_a_one_colour_picture_is_never_called_blurry():
    assert not is_blurry(Image.new("RGB", (720, 1280), (190, 120, 60)))
