"""After a script is written, a "Tự tìm ảnh" job gives every scene a free stock photo, marked for a member to check."""

import pytest
from conftest import first_topic, login, make_user, make_video
from sqlalchemy import select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixture)

from reels_api import auto_photos, jobs
from reels_api.models import AppSetting, Job, Scene, Video


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scripted(factory, storage, user) -> int:
    """A video whose script the (fake) LLM just wrote, its scenes without photos."""
    with factory() as db:
        video = Video(topic="canxi", knowledge_topic_id=first_topic(db).id, has_script=False, created_by_id=user.id)
        db.add(video)
        db.commit()
        video_id = video.id
    job_id = add_job(factory, video_id, user.id, kind="script", status="running")
    jobs.run_job(job_id, factory, storage)
    assert job_row(factory, job_id).status == "done"
    return video_id


def photos_job(factory, video_id) -> Job | None:
    with factory() as db:
        return db.scalar(select(Job).where(Job.video_id == video_id, Job.kind == "photos"))


def run_photos(factory, storage, video_id) -> Job:
    job = photos_job(factory, video_id)
    with factory() as db:
        db.get(Job, job.id).status = "running"
        db.commit()
    jobs.run_job(job.id, factory, storage)
    return job_row(factory, job.id)


def scenes_of(factory, video_id) -> list[Scene]:
    with factory() as db:
        return db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.position)).all()


# --- Queued after the script ---


def test_a_written_script_queues_the_photo_search(committed, fakes, storage):
    user = add_user(committed)
    video_id = scripted(committed, storage, user)
    job = photos_job(committed, video_id)
    assert (job.status, job.created_by_id) == ("queued", user.id)


def test_with_the_team_switch_off_no_search_is_queued(committed, fakes, storage):
    user = add_user(committed)
    with committed() as db:
        auto_photos.save(db, False, user.id)
        db.commit()
    video_id = scripted(committed, storage, user)
    assert photos_job(committed, video_id) is None


# --- The job ---


def test_every_scene_gets_a_different_tall_photo_marked_to_check(committed, fakes, storage):
    user = add_user(committed)
    video_id = scripted(committed, storage, user)

    job = run_photos(committed, storage, video_id)

    assert (job.status, job.error) == ("done", None)
    scenes = scenes_of(committed, video_id)
    assert all(scene.image_key and storage.exists(scene.image_key) for scene in scenes)
    assert all(scene.image_auto for scene in scenes)
    sources = [scene.image_source for scene in scenes]
    assert len(set(sources)) == len(sources), "no photo is used twice"
    assert all(query.get("orientation") == "vertical" for name, query in fakes.stock_searches if name == "pixabay")
    with committed() as db:
        assert db.get(Video, video_id).thumbnail_key is not None


def test_scenes_with_a_photo_or_clip_are_left_alone(committed, fakes, storage):
    user = add_user(committed)
    with committed() as db:
        video = make_video(db, storage, user)
        video_id = video.id
        first = db.scalar(select(Scene).where(Scene.video_id == video_id, Scene.is_title.is_(False)))
        kept = first.image_key
        first_id = first.id
        others = db.scalars(select(Scene).where(Scene.video_id == video_id, Scene.id != first_id)).all()
        for scene in others:
            scene.image_key, scene.image_source = None, None
        db.add(Job(video_id=video_id, kind="photos", status="queued", created_by_id=user.id))
        db.commit()

    run_photos(committed, storage, video_id)

    scenes = {scene.id: scene for scene in scenes_of(committed, video_id)}
    assert scenes[first_id].image_key == kept and not scenes[first_id].image_auto
    assert all(scene.image_key and scene.image_auto for scene_id, scene in scenes.items() if scene_id != first_id)


def test_pexels_is_asked_first(committed, fakes, storage):
    user = add_user(committed)
    video_id = scripted(committed, storage, user)

    run_photos(committed, storage, video_id)

    assert all(scene.image_key for scene in scenes_of(committed, video_id))
    assert fakes.stock_searches and all(name == "pexels" for name, _ in fakes.stock_searches)


def test_a_failing_source_moves_on_to_the_next(committed, fakes, storage):
    user = add_user(committed)
    video_id = scripted(committed, storage, user)
    fakes.pexels_mode = "error500"

    job = run_photos(committed, storage, video_id)

    assert job.status == "done"
    scenes = scenes_of(committed, video_id)
    assert all(scene.image_key for scene in scenes)
    assert fakes.pixabay_queries, "Pixabay, the next source, was asked"
    assert len(fakes.pexels_queries) == 1, "a source that failed is not asked again in the same job"


def test_a_turned_off_source_is_skipped(committed, fakes, storage):
    user = add_user(committed)
    video_id = scripted(committed, storage, user)
    with committed() as db:
        db.add(AppSetting(key="stock_sources_off", value=["pexels"]))
        db.commit()
    run_photos(committed, storage, video_id)
    assert fakes.pexels_queries == [] and all(scene.image_key for scene in scenes_of(committed, video_id))


def test_when_every_source_fails_the_job_says_so_and_the_script_stays(committed, fakes, storage):
    user = add_user(committed)
    video_id = scripted(committed, storage, user)
    fakes.pixabay_mode = "cloudflare_block"
    fakes.pexels_mode = "error500"
    fakes.openverse_mode = "error500"

    job = run_photos(committed, storage, video_id)

    assert job.status == "failed" and job.error.startswith("Không tự tìm được ảnh")
    assert not any(scene.image_key for scene in scenes_of(committed, video_id))
    with committed() as db:
        assert db.get(Video, video_id).has_script


def test_a_scene_nothing_is_found_for_stays_empty(committed, fakes, storage):
    user = add_user(committed)
    video_id = scripted(committed, storage, user)
    fakes.pixabay_mode = "empty"
    with committed() as db:
        db.add(AppSetting(key="stock_sources_off", value=["pexels", "openverse"]))
        db.commit()

    job = run_photos(committed, storage, video_id)

    assert job.status == "done"
    assert not any(scene.image_key for scene in scenes_of(committed, video_id))


# --- The mark ---


def test_choosing_another_photo_clears_the_mark(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.image_auto = True
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["scenes"][0]["image_auto"] is True

    from conftest import photo_bytes

    uploaded = an.post(f"/api/scenes/{scene.id}/image", files={"file": ("a.jpg", photo_bytes(), "image/jpeg")})
    assert uploaded.status_code == 200 and uploaded.json()["scenes"][0]["image_auto"] is False


def test_the_switch_is_on_the_sources_page_and_the_job_has_a_name(an, db, me, storage):
    assert an.get("/api/settings/sources").json()["auto_photos"] is True
    saved = an.put("/api/settings/auto-photos", json={"enabled": False})
    assert saved.status_code == 200 and saved.json()["auto_photos"] is False
    video = make_video(db, storage, me)
    db.add(Job(video_id=video.id, kind="photos", status="done", created_by_id=me.id))
    db.commit()
    row = next(row for row in an.get("/api/jobs").json() if row["kind"] == "photos")
    assert row["kind_label"] == "Tự tìm ảnh"


def test_keeping_the_pick_clears_the_mark(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.image_auto = True
    db.commit()
    kept = an.patch(f"/api/scenes/{scene.id}", json={"image_checked": True})
    assert kept.status_code == 200 and kept.json()["scenes"][0]["image_auto"] is False
