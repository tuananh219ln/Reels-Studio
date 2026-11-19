"""The "Cảnh kết Theo dõi & Chia sẻ" (outro.py): a group's switch ends its new videos on the shared outro scene in
place of the script's own call to action; its clip is rendered once and copied to every later video."""

import subprocess

import pytest
from conftest import first_topic, login, make_user, needs_ffmpeg
from sqlalchemy import select

from reels_api import jobs, motion, outro
from reels_api.models import Job, Scene, SceneSound


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scenes_of(db, video_id) -> list[Scene]:
    return list(
        db.scalars(
            select(Scene)
            .where(Scene.video_id == video_id, Scene.is_title.is_(False))
            .order_by(Scene.position)
            .execution_options(populate_existing=True)
        )
    )


def make(an, db, script):
    reply = an.post(
        "/api/videos",
        json={"knowledge_topic_id": first_topic(db).id, "mode": "manual", "topic": "xương khớp", "script": script},
    )
    assert reply.status_code == 201, reply.json()
    return reply.json()["id"]


SCRIPT = (
    "Vừng đen\nĐọc: Vừng đen giàu canxi.\n\n"
    "Cá hồi\nĐọc: Omega 3 trong cá hồi giảm đau khớp.\n\n"
    "Đọc: Theo dõi kênh và chia sẻ cho người thân nhé!"
)


def switch_on(db):
    group = first_topic(db)
    group.outro_cta = True
    db.flush()
    return group


def test_the_markup_passes_the_motion_checks_and_its_cache_key_follows_the_look():
    assert motion.check_markup(outro.HTML) == outro.HTML
    assert motion.check_seconds(outro.SECONDS) == outro.SECONDS
    assert outro.cache_key().startswith("outro/follow-share-") and outro.cache_key().endswith(".mp4")


def test_off_the_video_keeps_its_script_as_written(an, db):
    video_id = make(an, db, SCRIPT)
    scenes = scenes_of(db, video_id)
    assert len(scenes) == 3 and not any(outro.is_outro(scene) for scene in scenes)


def test_on_the_outro_takes_the_place_of_the_scripts_call_to_action(an, db):
    switch_on(db)
    video_id = make(an, db, SCRIPT)
    first, second, last = scenes_of(db, video_id)
    assert (first.text, second.text) == ("Vừng đen", "Cá hồi")
    assert outro.is_outro(last) and last.position == 3
    assert (last.text, last.voice_text, last.seconds, last.seconds_auto) == ("", outro.VOICE, 4.5, False)
    assert last.motion["html"] == outro.HTML and last.motion["clip_key"] is None and not last.motion["pending"]
    sounds = db.scalars(select(SceneSound).where(SceneSound.scene_id == last.id)).all()
    assert [(sound.sound, sound.start, sound.volume) for sound in sounds] == [("ding", 1.9, "normal")]
    assert db.scalar(select(Job).where(Job.video_id == video_id)) is None, (
        "the worker's round renders it, not a job now"
    )


def test_a_last_scene_that_asks_for_nothing_stays_before_the_outro(an, db):
    switch_on(db)
    video_id = make(an, db, "Vừng đen\nĐọc: Vừng đen giàu canxi.\n\nCá hồi\nĐọc: Omega 3 giảm đau khớp.")
    scenes = scenes_of(db, video_id)
    assert [scene.text for scene in scenes[:2]] == ["Vừng đen", "Cá hồi"] and outro.is_outro(scenes[2])


def test_the_script_prompt_tells_the_ai_to_leave_the_call_to_action_out(db):
    group = switch_on(db)
    assert outro.SCRIPT_FORMAT in jobs.script_prompt(group, "xương khớp", None, False, False)
    group.outro_cta = False
    assert outro.SCRIPT_FORMAT not in jobs.script_prompt(group, "xương khớp", None, False, False)


def test_the_round_renders_the_outro_once_and_the_others_wait(an, db, storage):
    switch_on(db)
    first = make(an, db, SCRIPT)
    second = make(an, db, SCRIPT)
    outro.fill(db, storage)
    queued = db.scalars(select(Job).where(Job.kind == "motion")).all()
    assert [(job.video_id, job.status) for job in queued] == [(first, "queued")]
    assert scenes_of(db, first)[-1].motion["pending"] is True
    outro.fill(db, storage)  # the render is under way: nothing more is queued
    assert len(db.scalars(select(Job).where(Job.kind == "motion")).all()) == 1
    assert scenes_of(db, second)[-1].motion["pending"] is False


def test_a_failed_outro_render_is_not_queued_again_by_the_round(an, db, storage):
    switch_on(db)
    video_id = make(an, db, SCRIPT)
    outro.fill(db, storage)
    job = db.scalar(select(Job).where(Job.kind == "motion"))
    job.status = "failed"
    motion.fail_pending(db, job)
    outro.fill(db, storage)
    assert db.scalars(select(Job).where(Job.video_id == video_id)).all() == [job]


def _cached_clip(tmp_path):
    clip = tmp_path / "outro.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=5"]
        + ["-pix_fmt", "yuv420p", "-c:v", "libx264", str(clip)],
        check=True,
    )
    return clip


@needs_ffmpeg
def test_a_rendered_outro_is_kept_and_later_videos_copy_it_without_a_render(an, db, storage, tmp_path):
    switch_on(db)
    waiting = make(an, db, SCRIPT)
    scene = scenes_of(db, waiting)[-1]
    outro.keep(storage, scene, _cached_clip(tmp_path))  # as motion.attach does after the first render
    assert storage.exists(outro.cache_key())
    outro.fill(db, storage)  # a scene made before the clip was kept gets it in the round
    filled = scenes_of(db, waiting)[-1]
    assert filled.video_key and filled.video_key == filled.motion["clip_key"] and storage.exists(filled.video_key)
    later = scenes_of(db, make(an, db, SCRIPT))[-1]  # made after: copied at once
    assert later.video_key and later.video_key != filled.video_key and later.seconds == 4.5
    assert db.scalar(select(Job).where(Job.kind == "motion")) is None


def test_another_scenes_motion_never_fills_the_cache(an, db, storage, tmp_path):
    video_id = make(an, db, SCRIPT)
    scene = scenes_of(db, video_id)[0]
    scene.motion = {"html": outro.HTML, "seconds": 4.5, "photo_key": None, "clip_key": None, "pending": True}
    outro.keep(storage, scene, tmp_path / "unused.mp4")
    assert not storage.exists(outro.cache_key())


def test_a_member_turns_the_switch_and_it_is_in_the_history(an, db):
    group = first_topic(db)
    shown = an.patch(f"/api/knowledge/topics/{group.id}", json={"outro_cta": True})
    assert shown.status_code == 200, shown.json()
    assert next(row for row in shown.json()["topics"] if row["id"] == group.id)["outro_cta"] is True
    history = an.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()["entries"]
    assert history[0]["changes"]["outro_cta"] == {"old": False, "new": True}
