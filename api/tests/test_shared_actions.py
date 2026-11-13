"""Entity actions expose ownership and cancellability consistently to every surface."""

from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api import article_posts
from reels_api.models import Article, Fanpage, Job, Publication
from reels_api.videos import publication_payload


def test_video_post_exposes_the_page_owner_for_take_down(db, storage):
    owner = make_user(db)
    author = make_user(db, email="author@doi.vn", name="Author")
    page = Fanpage(
        page_id="owner-actions", name="Owner Page", token_encrypted="unused", token_tail="used", owner_id=owner.id
    )
    db.add(page)
    video = make_video(db, storage, author, scene_count=1)
    post = Publication(
        video_id=video.id, fanpage=page, created_by_id=author.id, platform="facebook", status="scheduled"
    )
    db.add(post)
    db.commit()
    assert publication_payload(post, {})["fanpage_owner_id"] == owner.id


def test_article_post_exposes_the_page_owner_for_take_down(db):
    owner = make_user(db)
    author = make_user(db, email="author@doi.vn", name="Author")
    page = Fanpage(
        page_id="article-actions", name="Owner Page", token_encrypted="unused", token_tail="used", owner_id=owner.id
    )
    db.add(page)
    article = Article(created_by_id=author.id, kind="kien_thuc", topic="Shared actions")
    db.add(article)
    db.flush()
    post = Publication(
        article_id=article.id, fanpage=page, created_by_id=author.id, platform="facebook", status="scheduled"
    )
    db.add(post)
    db.commit()
    assert article_posts.post_payload(db, post, {})["fanpage_owner_id"] == owner.id


def test_job_log_exposes_only_backend_supported_cancellation(client, db, storage):
    user = make_user(db)
    login(client)
    for status, stage in (("queued", None), ("running", "ready"), ("running", None), ("failed", None)):
        video = make_video(db, storage, user, scene_count=1)
        db.add(Job(video_id=video.id, created_by_id=user.id, kind="render", status=status, node_stage=stage))
    db.commit()
    rows = client.get("/api/jobs?whose=all").json()
    jobs = db.scalars(select(Job).order_by(Job.id)).all()
    actual = {row["id"]: row["can_cancel"] for row in rows}
    assert [actual[job.id] for job in jobs] == [True, True, False, False]


def test_video_lists_name_the_queue_without_losing_video_identity(client, db, storage):
    from reels_api.models import PageQueueItem

    user = make_user(db)
    login(client)
    page = Fanpage(
        page_id="queue-actions", name="Queue Page", token_encrypted="unused", token_tail="used", owner_id=user.id
    )
    db.add(page)
    video = make_video(db, storage, user, scene_count=1)
    db.add(
        PageQueueItem(video_id=video.id, fanpage_id=page.id, position=0, added_by_id=user.id, error="Hãy render lại")
    )
    db.commit()
    listed = next(row for row in client.get("/api/videos").json() if row["id"] == video.id)
    assert listed["queue"]["fanpage"] == "Queue Page"
    assert listed["queue"]["error"] == "Hãy render lại"


def test_shared_post_read_requires_a_member_and_rejects_an_unknown_post(client, db):
    assert client.get("/api/posts/999").status_code == 401
    make_user(db)
    login(client)
    assert client.get("/api/posts/999").status_code == 404
    assert client.get("/api/affiliate-products/999").status_code == 404


def test_video_list_approval_time_follows_the_plan_and_is_absent_without_a_start(client, db, storage):
    from datetime import date

    from conftest import first_topic

    from reels_api.models import TopicPlanItem

    user = make_user(db)
    login(client)
    video = make_video(db, storage, user, scene_count=1)
    group = first_topic(db)
    db.add(
        TopicPlanItem(
            knowledge_topic_id=group.id, day=1, position=0, topic=video.topic, video_id=video.id, created_by_id=user.id
        )
    )
    db.commit()
    assert client.get("/api/videos").json()[0]["suggested_post_at"] is None
    group.plan_start_date, group.plan_post_times = date(2030, 1, 1), ["07:00"]
    db.commit()
    assert client.get("/api/videos").json()[0]["suggested_post_at"] == "2030-01-01T07:00:00+07:00"
