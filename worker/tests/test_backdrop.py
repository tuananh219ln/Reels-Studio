"""'Video xuyên suốt': the title scene's photo or clip under every scene, and photo layers ('Ảnh món') over it."""

import pytest
from conftest import extract_frame, make_clip, make_image, needs_ffmpeg, scene, write_script
from PIL import Image

from reels_render.errors import InputError
from reels_render.ffmpeg import probe
from reels_render.graph import SceneInput, build_ffmpeg_args, build_filter_graph, zoom_expression
from reels_render.layers import PHOTO_SHAPES, SIZES, Layer, render_layer, render_photo
from reels_render.options import RenderOptions
from reels_render.render import backdrop_start, render_video, trim_backdrop, with_backdrop
from reels_render.script import load_script
from reels_render.timeline import build_timeline

BACKDROP = RenderOptions(backdrop=True)


# --- Photo layers ---


@pytest.mark.parametrize("shape", [name for name in PHOTO_SHAPES if name != "plain"])
def test_a_framed_photo_has_a_white_edge_and_a_shadow_around_it(tmp_path, shape):
    photo = make_image(tmp_path / "dish.png", (800, 600), (200, 40, 40))
    picture = render_photo(photo, SIZES["medium"].photo, shape)
    assert picture.mode == "RGBA"
    # The photo plus room for the shadow on every side; circles and squares are cut square.
    inside = picture.width - 72
    assert inside == SIZES["medium"].photo
    if shape != "rounded":
        assert picture.height == picture.width
    middle = picture.getpixel((picture.width // 2, picture.height // 2))
    assert middle[:3] == (200, 40, 40) and middle[3] == 255
    # The white edge, just inside the photo's top middle.
    edge = picture.getpixel((picture.width // 2, 36 + 2))
    assert edge[0] > 240 and edge[1] > 240 and edge[2] > 240
    # The shadow: dark and partly transparent just below the photo, nothing at the canvas corner.
    below = picture.getpixel((picture.width // 2, picture.height - 36 + 4))
    assert 0 < below[3] < 255 and below[0] < 60
    assert picture.getpixel((0, 0))[3] == 0


def test_a_circle_is_transparent_in_its_corners(tmp_path):
    photo = make_image(tmp_path / "dish.png", (600, 600), (40, 160, 40))
    picture = render_photo(photo, 380, "circle")
    assert picture.getpixel((36 + 8, 36 + 8))[3] < 60


def test_a_plain_photo_keeps_its_own_transparency_and_gets_no_frame(tmp_path):
    cutout = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    cutout.paste((250, 200, 0, 255), (100, 100, 300, 300))
    cutout.save(tmp_path / "product.png")
    picture = render_photo(tmp_path / "product.png", 380, "plain")
    assert picture.size == (380, 380)
    assert picture.getpixel((5, 5))[3] == 0 and picture.getpixel((190, 190)) == (250, 200, 0, 255)


def test_photo_sizes_grow_and_a_tall_photo_is_cut(tmp_path):
    widths = [SIZES[name].photo for name in ("small", "medium", "large")]
    assert widths == sorted(widths) and widths[0] >= 1080 * 0.25 and widths[-1] <= 1080 * 0.8
    tall = make_image(tmp_path / "tall.jpg", (300, 1200))
    assert render_photo(tall, 700, "plain").size == (700, 1100)


def test_a_photo_layer_without_a_readable_photo_is_refused(tmp_path):
    with pytest.raises(ValueError, match="chưa có ảnh"):
        render_layer(Layer(kind="photo"))
    (tmp_path / "broken.jpg").write_bytes(b"not a photo")
    with pytest.raises(ValueError, match="không đọc được"):
        render_layer(Layer(kind="photo", image=tmp_path / "broken.jpg"))


def test_the_script_takes_a_photo_layer_with_its_frame(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    make_image(tmp_path / "dish.jpg", (600, 600))
    photo = {"kind": "photo", "image": "dish.jpg", "x": 300, "y": 700, "size": "large", "animation": "slide_up"}
    data = {"title": scene("TIÊU ĐỀ", 1), "scenes": [scene("Món 1", 2, layers=[photo])]}
    layer = load_script(write_script(tmp_path, data)).scenes[0].layers[0]
    assert (layer.kind, layer.style, layer.size, layer.image.name) == ("photo", "rounded", "large", "dish.jpg")
    for bad, message in (
        ({"image": ""}, 'lớp ảnh cần "image"'),
        ({"image": "missing.jpg"}, "không tìm thấy file ảnh"),
        ({"style": "outline"}, '"style" không hợp lệ'),
    ):
        data["scenes"][0]["layers"] = [photo | bad]
        with pytest.raises(InputError, match=message):
            load_script(write_script(tmp_path, data))


# --- The graph ---


def test_a_backdrop_video_joins_its_scenes_by_hard_cuts_and_fades_the_text():
    timeline = build_timeline([2, 3, 2])
    graph = build_filter_graph([(0, 0)] * 3, timeline, None, options=BACKDROP, transitions=[None, "wipe", None])
    assert "concat=n=3:v=1:a=0" in graph and "xfade" not in graph
    # The title's box is the cover: it only fades out; the last scene's only fades in.
    assert "[1:v]format=rgba,fade=t=out:st=1.700:d=0.300:alpha=1[t0]" in graph
    assert "[3:v]format=rgba,fade=t=in:st=0:d=0.300:alpha=1,fade=t=out:st=2.700:d=0.300:alpha=1[t1]" in graph
    assert "[5:v]format=rgba,fade=t=in:st=0:d=0.300:alpha=1[t2]" in graph
    assert "[bg1][t1]overlay" in graph


def test_a_slide_video_keeps_its_graph():
    timeline = build_timeline([2, 3])
    assert build_filter_graph([(0, 0)] * 2, timeline, None) == build_filter_graph(
        [(0, 0)] * 2, timeline, None, options=RenderOptions(backdrop=False), spans=[None, None]
    )


def test_a_backdrop_photo_moves_once_over_the_whole_video():
    assert zoom_expression(60, "zoom_in", 1.12, span=(60, 180)) == "1+0.1200*(on+60)/179"
    assert zoom_expression(60, "zoom_out", 1.12) == "1.1200-0.1200*on/59"
    graph = build_filter_graph(
        [(0, 0)] * 2, build_timeline([2, 4]), None, options=BACKDROP, spans=[(0, 180), (60, 180)]
    )
    assert "zoompan=z='1+0.1200*(on+0)/179'" in graph and "zoompan=z='1+0.1200*(on+60)/179'" in graph


def test_a_backdrop_clip_is_looped_and_each_text_box_lasts_its_scene(tmp_path):
    scenes = [
        SceneInput(
            image=tmp_path / "bg.mp4",
            text_box=tmp_path / f"t{index}.png",
            box_x=0,
            box_y=0,
            video_start=start,
            loop=True,
        )
        for index, start in enumerate((0.0, 2.0))
    ]
    argv = build_ffmpeg_args("ffmpeg", scenes, build_timeline([2, 3]), None, 0.25, tmp_path / "o.mp4", BACKDROP)
    text = " ".join(argv)
    assert "-stream_loop -1 -ss 2.000" in text
    assert f"-loop 1 -framerate 30 -t 3.000000 -i {tmp_path / 't1.png'}" in text


def test_each_scene_picks_up_the_clip_where_the_last_one_left_it():
    title = load_title_like(video_start=1.0, video_speed=1.0)
    assert backdrop_start(title, 0, 10.0) == 1.0
    assert backdrop_start(title, 90, 10.0) == 4.0  # frame 90 is 3 s in
    assert backdrop_start(title, 330, 10.0) == 2.0  # 1 + 11 s, wrapped into the 10 s clip
    fast = load_title_like(video_start=0.0, video_speed=2.0)
    assert backdrop_start(fast, 60, None) == 4.0


def load_title_like(video_start: float, video_speed: float):
    from reels_render.script import Scene

    return Scene("Cảnh tiêu đề", 0, "", [], 2, None, (), video_start=video_start, video_speed=video_speed)


def test_the_title_scene_must_have_a_backdrop(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    data = {"title": scene("TIÊU ĐỀ", 1, image=""), "scenes": [scene("Món 1", 2)]}
    with pytest.raises(InputError, match="Cảnh tiêu đề chưa có ảnh hoặc video"):
        with_backdrop(load_script(write_script(tmp_path, data)))


# --- Rendered ---


@needs_ffmpeg
def test_a_photo_layer_shows_over_a_backdrop_and_not_on_a_slide_video(tmp_path):
    make_image(tmp_path / "bg.jpg", (1080, 1920), (40, 80, 200))
    make_image(tmp_path / "own.jpg", (1080, 1920), (40, 200, 40))
    make_image(tmp_path / "dish.jpg", (600, 600), (220, 30, 30))
    photo = {"kind": "photo", "image": "dish.jpg", "start": 0, "seconds": 60, "x": 540, "y": 960, "size": "large"}
    data = {
        "title": scene("", 1, image="bg.jpg"),
        "scenes": [scene("", 2, image="own.jpg", layers=[photo]), scene("", 1, image="own.jpg")],
    }
    script = load_script(write_script(tmp_path, data))

    backdrop = render_video(script, tmp_path / "backdrop.mp4", options=BACKDROP)
    dish = extract_frame(backdrop, 2.0, tmp_path / "dish.png")
    assert dish.getpixel((540, 960))[0] > 180  # the dish photo, over the scene
    beside = dish.getpixel((540, 200))
    assert beside[2] > 150 and beside[1] < 130  # the title's blue backdrop, not the scene's own green photo
    last = extract_frame(backdrop, 3.5, tmp_path / "last.png").getpixel((540, 960))
    assert last[2] > 150  # the photo layer belongs to its scene only
    assert abs(float(probe("ffprobe", backdrop)["format"]["duration"]) - 4) < 0.1

    slides = render_video(script, tmp_path / "slides.mp4")
    own = extract_frame(slides, 2.0, tmp_path / "own.png").getpixel((540, 960))
    assert own[1] > 150 and own[0] < 120  # the scene's own photo, with no dish over it


@needs_ffmpeg
def test_a_short_backdrop_clip_loops_under_a_longer_video(tmp_path):
    make_clip(tmp_path / "bg.mp4", 1.5, "640x360")
    data = {
        "title": {"text": "TIÊU ĐỀ", "seconds": 1, "video": "bg.mp4"},
        "scenes": [scene("Ý một", 2, image=""), scene("Ý hai", 2, image="")],
    }
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4", options=BACKDROP)
    info = probe("ffprobe", output)
    assert abs(float(info["format"]["duration"]) - 5) < 0.1
    # The pattern keeps moving past the clip's 1.5 s: two frames a second apart differ.
    first = extract_frame(output, 3.2, tmp_path / "a.png")
    second = extract_frame(output, 3.7, tmp_path / "b.png")
    assert first.tobytes() != second.tobytes()


@needs_ffmpeg
def test_a_backdrop_clip_is_cut_at_the_title_start_so_it_loops_back_there(tmp_path):
    make_clip(tmp_path / "bg.mp4", 3, "640x360")
    data = {
        "title": {"text": "TIÊU ĐỀ", "seconds": 1, "video": "bg.mp4", "video_start": 1.0},
        "scenes": [scene("Ý một", 2, image="")],
    }
    script = with_backdrop(load_script(write_script(tmp_path, data)))
    work = tmp_path / "work"
    work.mkdir()
    cut = trim_backdrop("ffmpeg", script, work)
    assert {item.video for item in cut.all_scenes} == {work / "backdrop.mp4"}
    assert {item.video_start for item in cut.all_scenes} == {0.0}
    assert abs(float(probe("ffprobe", work / "backdrop.mp4")["format"]["duration"]) - 2) < 0.1
    # A clip used from its first second is left as it is.
    data["title"]["video_start"] = 0
    untouched = with_backdrop(load_script(write_script(tmp_path, data)))
    assert trim_backdrop("ffmpeg", untouched, work) is untouched


@needs_ffmpeg
def test_the_backdrop_stays_silent_whatever_a_scenes_own_sound(tmp_path):
    make_clip(tmp_path / "bg.mp4", 2, "640x360")
    data = {
        "title": {"text": "TIÊU ĐỀ", "seconds": 1, "video": "bg.mp4", "video_sound": True},
        "scenes": [{"text": "Ý một", "seconds": 2, "video": "bg.mp4", "video_sound": True}],
    }
    script = with_backdrop(load_script(write_script(tmp_path, data)))
    assert [(item.video_sound, item.words) for item in script.all_scenes] == [(False, ()), (False, ())]
