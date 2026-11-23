"""The "Tiêu đề động" (title_motion.py): the layout chosen from the listed scenes, the markup it builds, the sounds, and
the title scene's motion job with the switch Cổ điển / Động (a fake HyperFrames CLI on PATH, as in test_motion)."""

import json
from types import SimpleNamespace

import pytest
from conftest import make_video, needs_ffmpeg
from sqlalchemy import select
from test_motion import fake_hyperframes, needs_posix  # noqa: F401  (fake_hyperframes is a fixture)
from worker_helpers import add_user, committed, job_row  # noqa: F401  (committed is a fixture)

from reels_api import jobs, motion, title_motion
from reels_api.errors import ApiError
from reels_api.models import Job, Scene, Video


def atlas_for(layout, n):
    sizes = title_motion.slot_sizes(layout, n)
    width, height, offsets = title_motion.atlas_layout(sizes)
    return {"name": "photo.jpg", "width": width, "height": height, "sizes": sizes, "offsets": offsets}


@pytest.mark.parametrize(
    ("content_type", "title", "n", "layout"),
    [
        ("Danh sách món", "3 MÓN SÁNG", 3, "grid"),
        ("", "LO ĐƯỜNG HUYẾT? ĂN 4 TRÁI NÀY", 4, "grid"),
        ("Danh sách", "ĂN 5 RAU NÀY", 5, "grid"),
        ("", "6 MÓN CANH", 6, "grid"),
        ("", "NẤU 7 CANH NÀY", 7, "strip"),
        ("", "10 MÓN", 10, "strip"),
        ("Kết hợp", "TRỨNG + 7 LOẠI LÁ", 8, "ring"),
        ("", "TRỨNG KẾT HỢP VỚI 4 LOẠI LÁ", 5, "ring"),
        ("Món nên tránh", "TRÁNH 4 MÓN NÀY", 4, "warn"),
    ],
)
def test_the_layout_follows_the_kind_of_content_and_the_number_of_dishes(content_type, title, n, layout):
    assert title_motion.choose_layout(content_type, title, n) == layout


@pytest.mark.parametrize(("n", "requested"), [(1, "auto"), (11, "auto"), (7, "grid"), (4, "strip"), (4, "ring")])
def test_a_number_no_layout_holds_is_refused(n, requested):
    with pytest.raises(ApiError) as refused:
        title_motion.choose_layout("", "", n, requested)
    assert refused.value.status == 422


@pytest.mark.parametrize(
    ("layout", "n"),
    [("grid", n) for n in range(2, 7)] + [("warn", 4), ("ring", 8), ("ring", 5), ("strip", 7), ("strip", 10)],
)
def test_every_layout_builds_markup_the_motion_checks_accept_with_every_dish_popping_in(layout, n):
    atlas = atlas_for(layout, n)
    labels = [f"MÓN {i + 1}" for i in range(n)]
    markup = title_motion.build_html(layout, labels, atlas, "SỐ 4 ÍT AI NGỜ")
    assert motion.check_markup(markup) == markup.strip()
    assert all(f'tl.from(".s{i}"' in markup for i in range(n))
    assert "assets/photo.jpg" in markup and "http" not in markup
    assert atlas["height"] == sum(h for _, h in atlas["sizes"])
    assert (f'tl.to(".s{n - 1}"' in markup) is (layout != "warn")
    assert ('class="x"' in markup) is (layout == "warn")


def test_slots_stay_inside_the_area_below_the_hook_box():
    for layout, n in [("grid", 2), ("grid", 3), ("grid", 5), ("grid", 6), ("ring", 8), ("ring", 5)]:
        boxes = title_motion.grid_boxes(n) if layout == "grid" else title_motion.ring_boxes(n)
        for x, y, w, h in boxes:
            assert y >= 640 and y + h <= 1440 and x >= 0 and x + w <= 1080, (layout, n, (x, y, w, h))


def test_the_last_dish_is_hidden_behind_a_question_mark_with_its_line_when_the_slot_is_tall_enough():
    markup = title_motion.build_html("grid", ["A", "B", "C", "D"], atlas_for("grid", 4), "SỐ 4 ÍT AI NGỜ")
    assert markup.count('class="qm"') == 1 and "SỐ 4 ÍT AI NGỜ" in markup
    ring = title_motion.build_html("ring", ["A"] + list("BCDE"), atlas_for("ring", 5), "SỐ 4 ÍT AI NGỜ")
    assert "ÍT AI NGỜ" not in ring  # a bubble is too small for the line


def test_labels_are_escaped_in_the_markup():
    markup = title_motion.build_html("grid", ["<B>", "C"], atlas_for("grid", 2), "X")
    assert "&lt;B&gt;" in markup and "<B>" not in markup


def test_timing_pops_the_first_dish_at_a_tenth_of_a_second_and_the_last_shakes_after_it():
    starts, shake = title_motion.timing(4)
    assert starts == [0.1, 0.45, 0.8, 1.15] and shake == 1.7
    starts, _ = title_motion.timing(10)
    assert starts[0] == 0.1 and starts[-1] <= 1.4


def test_sounds_ding_each_dish_and_rise_before_the_hidden_one():
    assert title_motion.sounds("grid", 4) == [
        ("whoosh", 0.0, "soft"),
        ("ding", 0.1, "soft"),
        ("ding", 0.45, "soft"),
        ("ding", 0.8, "soft"),
        ("rise", 0.9, "normal"),
    ]
    many = title_motion.sounds("grid", 6)
    assert [s[0] for s in many].count("ding") == 3 and [s[0] for s in many].count("rise") == 1
    assert {name for name, _, _ in title_motion.sounds("warn", 4)} == {"whoosh", "wrong"}


def test_a_dishs_name_is_the_first_line_without_markup_numbers_or_the_explanation():
    label = title_motion.label_of
    assert label(Scene(text="*Bưởi* - giàu vitamin C")) == "BƯỞI"
    assert label(Scene(text="2. Thanh long\nGiàu chất xơ")) == "THANH LONG"
    assert label(Scene(text="Ổi: tốt cho đường huyết")) == "ỔI"
    assert len(label(Scene(text="Một món có cái tên dài khủng khiếp không vừa ô"))) <= title_motion.MAX_LABEL


def test_banned_health_words_in_the_hook_are_reported():
    scene = Scene(text="ĂN BƯỞI CHỮA TIỂU ĐƯỜNG", voice_text="Hơn cả thuốc, 100% hiệu quả")
    found = title_motion.hook_warnings(scene)
    assert len(found) == 3 and all("nên tránh" in line for line in found)
    assert title_motion.hook_warnings(Scene(text="LO ĐƯỜNG HUYẾT?", voice_text="")) == []


def test_the_hook_follows_the_specs_sentences():
    hook = title_motion.hook_lines
    assert hook("grid", 4, "đường huyết", "TRÁI") == "LO ĐƯỜNG HUYẾT?\nĂN 4 TRÁI NÀY"
    assert hook("strip", 7, "", "CANH") == "ĂN 7 CANH NÀY"
    assert hook("ring", 8, "", "LÁ", "TRỨNG") == "TRỨNG + 7 LOẠI LÁ\nSỐ 7 ÍT AI BIẾT"
    assert hook("ring", 5, "", "", "TRỨNG") == "TRỨNG + 4 LOẠI\nSỐ 4 ÍT AI BIẾT"
    assert hook("warn", 4, "đường huyết cao", "") == "ĐƯỜNG HUYẾT CAO\nTRÁNH 4 MÓN NÀY"


def test_the_hook_is_read_with_numbers_in_words():
    voice = title_motion.hook_voice
    assert voice("grid", 4, "đường huyết", "TRÁI") == "Lo đường huyết? Ăn bốn loại trái cây này."
    assert voice("strip", 7, "", "CANH") == "Ăn bảy món canh này."
    assert voice("ring", 8, "", "RAU", "Trứng") == "Trứng kết hợp bảy loại rau, loại thứ bảy ít ai biết."
    assert voice("warn", 4, "huyết áp cao", "") == "Huyết áp cao? Tránh bốn món này."


def test_the_crop_leans_towards_the_colourful_sharp_part_of_the_photo():
    from PIL import Image, ImageDraw

    photo = Image.new("RGB", (400, 400), (120, 120, 120))
    ImageDraw.Draw(photo).ellipse((260, 20, 380, 140), fill=(230, 40, 30))
    x, y = title_motion.subject_centre(photo)
    assert x > 0.55 and y < 0.45
    assert title_motion.subject_centre(Image.new("RGB", (400, 400), (120, 120, 120))) == (0.5, 0.5)


def test_the_dishes_word_comes_from_the_topic():
    assert title_motion.noun_of("4 trái cây tốt cho đường huyết") == "TRÁI"
    assert title_motion.noun_of("Ăn rau nào cho gan") == "RAU"
    assert title_motion.noun_of("Bí quyết sống khỏe") == ""


# --- The job and the switch, in process on committed rows ---


def queue(factory, storage, **options):
    user = add_user(factory)
    with factory() as db:
        video = make_video(db, storage, user, scene_count=4)
        video.content_type = "Danh sách món"
        db.commit()
        title = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(True)))
        before = title.image_key
        _, warnings = title_motion.build(db, storage, title.id, SimpleNamespace(user_id=user.id), **options)
        job = db.scalar(select(Job).where(Job.video_id == video.id))
        assert (job.kind, job.status, job.scene_id) == ("motion", "queued", title.id)
        job.status = "running"
        db.commit()
        return job.id, title.id, before, warnings


@needs_ffmpeg
@needs_posix
def test_the_title_scene_gets_its_motion_clip_keeps_its_photo_and_its_sounds(committed, storage, fake_hyperframes):  # noqa: F811
    job_id, title_id, photo, warnings = queue(committed, storage)
    assert warnings == []
    jobs.run_job(job_id, committed, storage)
    assert job_row(committed, job_id).status == "done"
    with committed() as db:
        title = db.get(Scene, title_id)
        made = title.motion
        assert title.video_key == made["clip_key"] and title.image_key is None
        assert made["classic"]["image_key"] == photo and storage.exists(photo)  # "Cổ điển" keeps its photo
        assert made["title"]["layout"] == "grid" and made["title"]["count"] == 4 and made["seconds"] == 3.0
        assert (title.text_x, title.text_y) == (540, 400)
        assert [(s.sound, s.start) for s in title.sounds][0] == ("whoosh", 0.0)
        assert [s.sound for s in title.sounds].count("rise") == 1
    report = json.loads(fake_hyperframes.read_text(encoding="utf-8"))
    assert "photo.jpg" in report["assets"] and 'class="qm"' in report["html"]


@needs_ffmpeg
@needs_posix
def test_the_switch_goes_back_and_forth_without_a_new_job(committed, storage, fake_hyperframes):  # noqa: F811
    job_id, title_id, photo, _ = queue(committed, storage)
    jobs.run_job(job_id, committed, storage)
    with committed() as db:
        clip = db.get(Scene, title_id).motion["clip_key"]
        title_motion.set_mode(db, storage, title_id, "classic")
        title = db.get(Scene, title_id)
        assert (title.image_key, title.video_key) == (photo, None) and storage.exists(clip)
        assert db.scalars(select(Job).where(Job.status.in_(("queued", "running")))).first() is None
        title_motion.set_mode(db, storage, title_id, "motion")
        title = db.get(Scene, title_id)
        assert (title.video_key, title.image_key, title.seconds) == (clip, None, 3.0)
        assert title.motion["classic"]["image_key"] == photo and storage.exists(photo)


def test_an_empty_title_gets_the_hook_and_a_written_one_is_kept_unless_asked(committed, storage):  # noqa: F811
    user = add_user(committed)
    me = SimpleNamespace(user_id=user.id)
    with committed() as db:
        video = make_video(db, storage, user, scene_count=4, topic="4 trái cây cho đường huyết")
        title = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(True)))
        kept = title.text
        title_motion.build(db, storage, title.id, me)
        assert db.get(Scene, title.id).text == kept
        for job in db.scalars(select(Job).where(Job.video_id == video.id)):
            job.status = "done"
        db.commit()
        title_motion.build(db, storage, title.id, me, write_hook=True)
        assert db.get(Scene, title.id).text == "ĂN 4 TRÁI NÀY"
        assert db.get(Scene, title.id).voice_text == "Ăn bốn loại trái cây này."


def test_only_the_title_scene_takes_a_title_motion(committed, storage):  # noqa: F811
    user = add_user(committed)
    with committed() as db:
        video = make_video(db, storage, user, scene_count=4)
        scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
        with pytest.raises(ApiError) as refused:
            title_motion.build(db, storage, scene.id, SimpleNamespace(user_id=user.id))
        assert refused.value.status == 422


def test_a_listed_scene_without_a_photo_is_named_and_nothing_is_queued(committed, storage):  # noqa: F811
    user = add_user(committed)
    with committed() as db:
        video = make_video(db, storage, user, scene_count=4)
        title = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(True)))
        third = db.scalars(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False))).all()[2]
        third.image_key = None
        db.commit()
        with pytest.raises(ApiError) as refused:
            title_motion.build(db, storage, title.id, SimpleNamespace(user_id=user.id))
        assert "số 3" in refused.value.message
        db.rollback()
        assert db.scalar(select(Job).where(Job.video_id == video.id)) is None
        assert db.get(Video, video.id).has_script


def test_slots_keep_only_what_a_member_set_and_refuse_a_scene_of_another_video(committed, storage):  # noqa: F811
    user = add_user(committed)
    with committed() as db:
        video = make_video(db, storage, user, scene_count=4)
        other = make_video(db, storage, user, scene_count=2)
        mine = db.scalars(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False))).all()
        foreign = db.scalar(select(Scene).where(Scene.video_id == other.id, Scene.is_title.is_(False)))
        got = title_motion.clean_slots(
            db, video, [{"label": " bưởi ", "focus": [0.2, 0.8]}, {"from_scene": mine[3].id}, {"focus": [2, 0]}], 4
        )
        assert got == [{"label": "BƯỞI", "focus": [0.2, 0.8]}, {"from_scene": mine[3].id}, {}, {}]
        with pytest.raises(ApiError):
            title_motion.clean_slots(db, video, [{"from_scene": foreign.id}], 4)


@needs_ffmpeg
@needs_posix
def test_a_slots_own_photo_is_kept_by_a_rebuild_and_replaced_by_the_next(committed, storage, fake_hyperframes):  # noqa: F811
    from conftest import photo_bytes

    job_id, title_id, _, _ = queue(committed, storage)
    jobs.run_job(job_id, committed, storage)
    with committed() as db:
        title_motion.set_slot_photo(db, storage, title_id, 1, photo_bytes((250, 10, 10)), "jpg")
        first = db.get(Scene, title_id).motion["title"]["slots"][1]["image_key"]
        assert storage.exists(first)
        with pytest.raises(ApiError):
            title_motion.set_slot_photo(db, storage, title_id, 9, photo_bytes((1, 2, 3)), "jpg")
        title_motion.set_slot_photo(db, storage, title_id, 1, photo_bytes((10, 10, 250)), "jpg")
        second = db.get(Scene, title_id).motion["title"]["slots"][1]["image_key"]
        assert second != first and not storage.exists(first) and storage.exists(second)
        title_motion.build(
            db, storage, title_id, SimpleNamespace(user_id=db.get(Scene, title_id).video.created_by_id), slots=[]
        )
        assert db.get(Scene, title_id).motion["title"]["slots"][1]["image_key"] == second


@needs_ffmpeg
@needs_posix
def test_a_page_set_to_classic_keeps_the_first_built_title_on_its_own_photo(committed, storage, fake_hyperframes):  # noqa: F811
    from reels_api.models import Brand

    user = add_user(committed)
    with committed() as db:
        brand = Brand(name="Kênh thử", slug="kenh-thu", owner_id=user.id, title_style="classic")
        db.add(brand)
        video = make_video(db, storage, user, scene_count=4)
        video.content_type = "Danh sách món"
        video.options = {**(video.options or {}), "brand_id": brand.id}
        db.commit()
        title = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(True)))
        photo, title_id = title.image_key, title.id
        title_motion.build(db, storage, title_id, SimpleNamespace(user_id=user.id))
        job = db.scalar(select(Job).where(Job.video_id == video.id))
        job.status = "running"
        db.commit()
        job_id = job.id
    jobs.run_job(job_id, committed, storage)
    with committed() as db:
        title = db.get(Scene, title_id)
        assert (title.image_key, title.video_key) == (photo, None)
        assert title.motion["clip_key"] and storage.exists(title.motion["clip_key"])
        title_motion.set_mode(db, storage, title_id, "motion")
        assert db.get(Scene, title_id).video_key == title.motion["clip_key"]
