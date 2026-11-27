"""'Ẩn chữ sau X giây': a video's and a scene's own hold, PC Shopee's default, and what reaches the render."""

import pytest
from conftest import login, make_user, make_video
from test_text_position import scene_json

from reels_api import video_options
from reels_api.models import KnowledgeTopic
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.mark.parametrize("value", [None, 1, 1.0, 2.5, 3.5, 6])
def test_a_hold_of_one_to_six_seconds_in_half_steps_is_accepted(value):
    assert video_options.clean({"text_hold_sec": value}) == {"text_hold_sec": None if value is None else float(value)}


@pytest.mark.parametrize("value", [0.5, 6.5, 2.2, "2.5", True, -1])
def test_any_other_hold_is_refused(value):
    with pytest.raises(video_options.OptionError, match="Thời gian hiện chữ"):
        video_options.clean({"text_hold_sec": value})


def test_the_default_is_the_whole_scene_and_changes_no_mp4(db, me, storage):
    assert video_options.DEFAULTS["text_hold_sec"] is None
    video = make_video(db, storage, me)
    before = render_signature(video, *split_scenes(db, video))
    video.options = dict(video_options.DEFAULTS)
    assert render_signature(video, *split_scenes(db, video)) == before
    video.options = video_options.DEFAULTS | {"text_hold_sec": 2.5}
    assert render_signature(video, *split_scenes(db, video)) != before


def test_a_scene_own_hold_wins_over_the_video_and_the_title_has_none(an, db, me, storage):
    video = make_video(db, storage, me)
    video.options = video_options.DEFAULTS | {"text_hold_sec": 2.5}
    db.commit()
    title, scenes = split_scenes(db, video)
    assert video_options.text_hold(video, title) is None
    assert video_options.text_hold(video, scenes[0]) == 2.5

    saved = an.patch(f"/api/scenes/{scenes[0].id}", json={"text_hold_sec": 3.5})
    assert saved.status_code == 200
    assert scene_json(saved.json(), scenes[0].id)["text_hold_sec"] == 3.5
    db.refresh(scenes[0])
    assert video_options.text_hold(video, scenes[0]) == 3.5
    assert video_options.text_hold(video, scenes[1]) == 2.5  # the other scenes follow the video

    an.patch(f"/api/scenes/{scenes[0].id}", json={"text_hold_sec": None})
    db.refresh(scenes[0])
    assert video_options.text_hold(video, scenes[0]) == 2.5


def test_a_scene_refuses_a_bad_hold_and_the_title_refuses_any(an, db, me, storage):
    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    assert an.patch(f"/api/scenes/{scenes[0].id}", json={"text_hold_sec": 7}).status_code == 422
    refused = an.patch(f"/api/scenes/{title.id}", json={"text_hold_sec": 2.5})
    assert refused.status_code == 422 and "Cảnh tiêu đề" in refused.json()["message"]


def test_only_pc_shopee_starts_new_videos_with_a_hold(db, me, storage):
    other = make_video(db, storage, me)
    group = db.get(KnowledgeTopic, other.knowledge_topic_id)
    assert not video_options.is_pc_shopee(group)
    video_options.apply_defaults(db, other, me.id)
    assert other.options["text_hold_sec"] is None  # every other group: as before

    shopee = KnowledgeTopic(name=" pc shopee ")
    db.add(shopee)
    db.flush()
    video = make_video(db, storage, me)
    video.knowledge_topic_id = shopee.id
    video_options.apply_defaults(db, video, me.id)
    assert video_options.is_pc_shopee(shopee)
    assert video.options["text_hold_sec"] == video_options.PC_SHOPEE_TEXT_HOLD == 2.5
    assert (video.options["title_layout"], video.options["scene_text_layout"]) == ("three_tier", "two_tier")
    assert (other.options["title_layout"], other.options["scene_text_layout"]) == ("box", "box")
    assert video.options["captions"] == "cumulative"  # "Cộng dồn" is PC Shopee's default; every other group's is off
    assert other.options["captions"] == "off"


def test_the_pc_shopee_look_changes_the_mp4_only_when_it_is_not_the_default(db, me, storage):
    video = make_video(db, storage, me)
    video.options = video_options.DEFAULTS | {"transition": "cut"}
    before = render_signature(video, *split_scenes(db, video))
    video.options = video_options.DEFAULTS | {"transition": "cut", "pc_style": "neon_game"}
    assert render_signature(video, *split_scenes(db, video)) == before  # the default look leaves the fingerprint alone
    video.options = video_options.DEFAULTS | {"transition": "cut", "pc_style": "brand_navy"}
    assert render_signature(video, *split_scenes(db, video)) != before


def test_pc_shopee_tiers_warn_in_yellow_about_a_line_too_long_and_still_render(db, me, storage):
    from reels_api.videos import run_checks

    video = make_video(db, storage, me, scene_count=3)
    title, scenes = split_scenes(db, video)
    title.text = "BLACK FRIDAY\n5 MÓN PC ĐÁNG SĂN NHẤT NĂM\nGIẢM THẬT"
    scenes[0].text = "1. *LOGITECH G304 KHÔNG DÂY*\nbàn gọn hẳn đi nhiều lắm"
    scenes[-1].text = "DEAL HẤP DẪN QUÁ LÀ DÀI\nMÌNH ĐỂ DƯỚI BÌNH LUẬN"  # the call to action stays a box: never warned
    before = {issue.message for issue in run_checks(db, video, title, scenes).warnings}
    video.options = video_options.DEFAULTS | {"title_layout": "three_tier", "scene_text_layout": "two_tier"}
    checks = run_checks(db, video, title, scenes)
    new = [issue for issue in checks.warnings if issue.message not in before]
    assert any("tiêu đề" in issue.message and issue.scene_id == title.id for issue in new)
    assert any("quá dài" in issue.message and issue.scene_id == scenes[0].id for issue in new)
    assert not any(issue.scene_id == scenes[-1].id for issue in new)
    assert not checks.blocking or all("tiêu đề" not in issue.message for issue in checks.blocking)


def test_a_content_scene_takes_top_or_the_lower_zone_and_nothing_else(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = split_scenes(db, video)[1][0]
    before = render_signature(video, *split_scenes(db, video))
    saved = an.patch(f"/api/scenes/{scene.id}", json={"text_zone": "top"})
    assert saved.status_code == 200 and scene_json(saved.json(), scene.id)["text_zone"] == "top"
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != before
    assert an.patch(f"/api/scenes/{scene.id}", json={"text_zone": "middle"}).status_code == 422
    an.patch(f"/api/scenes/{scene.id}", json={"text_zone": None})
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == before  # back to the lower zone: the MP4 stays current


def test_the_groups_own_look_wins_over_pc_shopee_starting_values(db, me, storage):
    shopee = KnowledgeTopic(name="PC Shopee", text_look={"captions": "word", "text_hold_sec": 3.5})
    db.add(shopee)
    db.flush()
    video = make_video(db, storage, me)
    video.knowledge_topic_id = shopee.id
    video_options.apply_defaults(db, video, me.id)
    assert video.options["captions"] == "word" and video.options["text_hold_sec"] == 3.5  # the group's choices
    assert video.options["title_layout"] == "three_tier"  # what it did not choose keeps PC Shopee's start


def test_compact_text_with_phrase_or_word_captions_goes_after_2_5_seconds_unless_a_hold_is_chosen():
    from reels_api.models import Scene, Video

    scene = Scene(is_title=False)
    for captions, layout, own, expected in (
        ("word", "two_tier", None, 2.5),  # the text and the captions are never on screen together
        ("phrase", "two_tier", None, 2.5),
        ("word", "two_tier", 3.5, 3.5),  # a hold chosen wins
        ("cumulative", "two_tier", None, None),  # "Cộng dồn" has no scene text at all
        ("word", "box", None, None),  # the text boxes of every other group: as before
        ("off", "two_tier", None, None),
    ):
        video = Video(options=video_options.DEFAULTS | {"captions": captions, "scene_text_layout": layout})
        scene.text_hold_sec = own
        assert video_options.text_hold(video, scene) == expected, (captions, layout, own)
    assert video_options.text_hold(video, Scene(is_title=True)) is None
