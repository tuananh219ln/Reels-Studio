"""Posting articles ("Bài viết"): the endpoints, the publish/unpublish/check jobs, the products' comment, the numbers
and their analysis, and that reels are left as they were."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from worker_helpers import add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import analytics, article_posts, articles, fanpages, jobs, metrics, post_comments
from reels_api.models import (
    AffiliateProduct,
    Article,
    ArticleAffiliateProduct,
    Fanpage,
    Job,
    PageComment,
    PostMetrics,
    Publication,
    Video,
)
from reels_api.storage import DirectoryStorage

CAPTION = (
    "Ngủ đủ giấc quan trọng hơn bạn nghĩ\n\nNội dung\nAi có bệnh nền thì hỏi bác sĩ trước nhé.\n\nBạn ngủ mấy tiếng?"
)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def page_id(db, user, page=FACEBOOK_PAGE, name="Trang Dưỡng Sinh") -> int:
    row = fanpages.save(db, page, name, FACEBOOK_TOKEN, user.id)
    db.commit()
    return row.id


def in_minutes(minutes: float) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def ago(minutes: float) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def add_article(db, user, caption=CAPTION, **fields) -> Article:
    article = Article(
        knowledge_topic_id=first_topic(db).id,
        kind="kien_thuc",
        topic="Ngủ đủ giấc",
        caption=caption,
        hashtags=["#suckhoe"],
        created_by_id=user.id,
        **fields,
    )
    db.add(article)
    db.commit()
    return article


def add_product(db, user, name="Gối cao su") -> AffiliateProduct:
    product = AffiliateProduct(
        knowledge_topic_id=first_topic(db).id,
        name=name,
        url=f"https://s.shopee.vn/{len(name)}",
        shop_name="Shop",
        shop_type="mall",
        rating=4.9,
        sold=1000,
        price=200000,
        commission_rate=8,
        status="approved",
        created_by_id=user.id,
    )
    db.add(product)
    db.commit()
    return product


# --- The endpoints ---


def test_posting_queues_a_job_and_locks_the_article(an, db, me):
    article = add_article(db, me)
    saved = an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": page_id(db, me)}).json()
    assert (saved["status"], saved["status_label"], saved["busy"]) == ("publishing", "Đang đăng…", True)
    (post,) = saved["posts"]
    assert (post["status"], post["fanpage"], post["url"]) == ("pending", "Trang Dưỡng Sinh", None)
    job = db.scalar(select(Job).where(Job.article_id == article.id))
    assert (job.kind, job.video_id) == ("publish", None)
    refused = an.patch(f"/api/articles/{article.id}", json={"caption": "khác"})
    assert refused.status_code == 409


def test_a_caption_with_a_link_or_none_is_not_posted(an, db, me):
    pid = page_id(db, me)
    empty = add_article(db, me, caption="")
    linked = add_article(db, me, caption="Mua ở shope.ee/abc")
    for article, message in (
        (empty, "Chưa có caption"),
        (linked, "Caption có link: link sản phẩm chỉ để ở bình luận ghim"),
    ):
        refused = an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": pid})
        assert (refused.status_code, refused.json()["message"]) == (409, message)


@pytest.mark.parametrize("minutes", [14, 29 * 24 * 60 + 5])
def test_the_scheduled_time_must_be_one_facebook_accepts(an, db, me, minutes):
    article = add_article(db, me)
    refused = an.post(
        f"/api/articles/{article.id}/publish", json={"fanpage_id": page_id(db, me), "scheduled_at": in_minutes(minutes)}
    )
    assert refused.status_code == 422


def test_the_same_caption_is_refused_on_its_page_and_asks_first_on_another(an, db, me):
    first, second = page_id(db, me), page_id(db, me, "222", "Trang Hai")
    posted = add_article(db, me)
    db.add(
        Publication(
            article_id=posted.id,
            platform="facebook",
            fanpage_id=first,
            status="published",
            remote_id="x_1",
            post_text=f"{CAPTION}\n\n#suckhoe",
            created_by_id=me.id,
        )
    )
    db.commit()
    # Accents, case, spaces and hashtags do not make it new.
    again = add_article(db, me, caption=CAPTION.upper().replace("NGỦ", "NGU").replace("\n\n", "  \n"))
    refused = an.post(f"/api/articles/{again.id}/publish", json={"fanpage_id": first})
    assert (refused.status_code, refused.json()["code"]) == (409, "already_on_page")
    asked = an.post(f"/api/articles/{again.id}/publish", json={"fanpage_id": second})
    assert (asked.status_code, asked.json()["code"]) == (409, "confirm_needed")
    assert "Trang Dưỡng Sinh" in asked.json()["message"]
    confirmed = an.post(f"/api/articles/{again.id}/publish", json={"fanpage_id": second, "confirm": True})
    assert confirmed.status_code == 200 and confirmed.json()["posts"][0]["fanpage"] == "Trang Hai"


def test_a_reel_scheduled_within_two_hours_on_the_page_asks_first(an, db, me, storage):
    pid = page_id(db, me)
    video = make_video(db, storage, me, scene_count=1)
    at = datetime.now(UTC) + timedelta(hours=3)
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            fanpage_id=pid,
            status="scheduled",
            scheduled_at=at,
            created_by_id=me.id,
        )
    )
    db.commit()
    article = add_article(db, me)
    near = (at + timedelta(minutes=90)).isoformat()
    asked = an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": pid, "scheduled_at": near})
    assert asked.json()["message"] == "Page này có reel hẹn giờ trong vòng 2 giờ quanh giờ đăng bài."
    far = (at + timedelta(hours=2, minutes=5)).isoformat()
    assert (
        an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": pid, "scheduled_at": far}).status_code == 200
    )


def test_taking_down_a_post_facebook_never_got_cancels_it_and_its_job(an, db, me):
    article = add_article(db, me)
    saved = an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": page_id(db, me)}).json()
    post_id = saved["posts"][0]["id"]
    after = an.post(f"/api/articles/posts/{post_id}/take-down").json()
    assert after["posts"][0]["status"] == "cancelled" and after["status"] == "draft" and after["busy"] is False
    assert db.scalar(select(Job.status).where(Job.article_id == article.id)) == "cancelled"


def test_taking_down_a_live_post_goes_through_the_worker_and_a_posted_article_stays(an, db, me):
    article = add_article(db, me)
    db.add(
        Publication(
            article_id=article.id,
            platform="facebook",
            fanpage_id=page_id(db, me),
            status="published",
            remote_id="x_2",
            created_by_id=me.id,
        )
    )
    db.commit()
    post_id = db.scalar(select(Publication.id).where(Publication.article_id == article.id))
    refused = an.delete(f"/api/articles/{article.id}")
    assert (refused.status_code, refused.json()["code"]) == (409, "article_posted")
    saved = an.post(f"/api/articles/posts/{post_id}/take-down").json()
    assert saved["status"] == "unpublishing"
    job = db.scalar(select(Job).where(Job.article_id == article.id))
    assert (job.kind, job.publication_id) == ("unpublish", post_id)


def test_reel_endpoints_do_not_take_an_article_post(an, db, me):
    article = add_article(db, me)
    db.add(
        Publication(
            article_id=article.id,
            platform="facebook",
            fanpage_id=page_id(db, me),
            status="published",
            remote_id="x_3",
            created_by_id=me.id,
        )
    )
    db.commit()
    post_id = db.scalar(select(Publication.id).where(Publication.article_id == article.id))
    for path in ("take-down", "check", "comment", "metrics"):
        assert an.post(f"/api/posts/{post_id}/{path}").status_code == 404, path
    # "Bài đăng" lists reels only.
    assert an.get("/api/posts").json() == []


def test_products_at_most_two_approved_ones_and_the_caption_points_at_the_comment(an, db, me):
    article = add_article(db, me)
    one, two, three = (add_product(db, me, name) for name in ("Gối", "Đệm", "Chăn"))
    draft = add_product(db, me, "Nháp")
    draft.status = "draft"
    db.commit()
    assert (
        an.put(f"/api/articles/{article.id}/products", json={"product_ids": [one.id, two.id, three.id]}).status_code
        == 422
    )
    assert an.put(f"/api/articles/{article.id}/products", json={"product_ids": [draft.id]}).status_code == 422
    choices = an.get(f"/api/articles/{article.id}/product-choices").json()
    assert {row["name"] for row in choices} == {"Gối", "Đệm", "Chăn"}
    saved = an.put(f"/api/articles/{article.id}/products", json={"product_ids": [one.id, two.id]}).json()
    assert [product["name"] for product in saved["products"]] == ["Gối", "Đệm"]
    assert saved["post_text"] == f"{CAPTION}\n\n{article_posts.PRODUCT_LINE}\n\n#suckhoe"
    assert "shopee" not in saved["post_text"]
    posted = an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": page_id(db, me)}).json()
    assert posted["posts"][0]["comment"]["auto"] is True


def test_make_a_reel_from_an_article_starts_a_video_on_its_topic(an, db, me):
    article = add_article(db, me)
    made = an.post(f"/api/articles/{article.id}/make-video")
    assert made.status_code == 201
    video = db.get(Video, made.json()["video_id"])
    assert (video.topic, video.knowledge_topic_id) == ("Ngủ đủ giấc", article.knowledge_topic_id)
    assert db.scalar(select(Job.kind).where(Job.video_id == video.id)) == "script"


# --- The jobs ---


@pytest.fixture
def ready(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        db.flush()
        article = add_article(db, user)
        db.add(Publication(article_id=article.id, platform="facebook", fanpage_id=page.id, created_by_id=user.id))
        db.commit()
        return user, storage, article.id


def run(factory, storage, article_id, user_id, kind="publish", publication_id=None) -> Job:
    with factory() as db:
        job = Job(
            article_id=article_id, kind=kind, status="running", created_by_id=user_id, publication_id=publication_id
        )
        db.add(job)
        db.commit()
    jobs.run_job(job.id, factory, storage)
    return job_row(factory, job.id)


def post_of(factory, article_id) -> Publication:
    with factory() as db:
        return db.scalar(select(Publication).where(Publication.article_id == article_id))


def test_a_text_post_goes_out_with_its_hashtags(committed, ready, fakes):
    user, storage, article_id = ready
    job = run(committed, storage, article_id, user.id)
    assert job.status == "done", job.error
    post = post_of(committed, article_id)
    (remote,) = fakes.page_posts.values()
    assert (remote["edge"], remote["published"], remote["photo"]) == ("feed", True, None)
    assert remote["message"] == f"{CAPTION}\n\n#suckhoe" == post.post_text
    assert (post.status, post.remote_id) == ("published", next(iter(fakes.page_posts)))


def test_a_photo_post_sends_the_picture_and_a_scheduled_one_waits(committed, ready, fakes):
    user, storage, article_id = ready
    storage.save_bytes("articles/1/card.jpg", articles.text_card("Ngủ đủ giấc", "cam"))
    at = datetime.now(UTC) + timedelta(hours=5)
    with committed() as db:
        db.get(Article, article_id).image_key = "articles/1/card.jpg"
        post = db.scalar(select(Publication).where(Publication.article_id == article_id))
        post.scheduled_at = at
        db.commit()
    assert run(committed, storage, article_id, user.id).status == "done"
    (remote,) = fakes.page_posts.values()
    assert remote["edge"] == "photos" and remote["photo"].startswith(b"\xff\xd8")
    assert (remote["published"], remote["scheduled"]) == (False, int(at.timestamp()))
    post = post_of(committed, article_id)
    assert post.status == "scheduled" and abs(post.scheduled_at - at) < timedelta(seconds=1)


def test_a_retry_after_a_lost_answer_finds_the_post_instead_of_posting_again(committed, ready, fakes):
    user, storage, article_id = ready
    fakes.page_post_replies_lost = 1
    assert run(committed, storage, article_id, user.id).status == "failed"
    assert post_of(committed, article_id).finish_sent_at is not None
    assert run(committed, storage, article_id, user.id).status == "done"
    assert fakes.page_post_calls == 1 and len(fakes.page_posts) == 1
    assert post_of(committed, article_id).remote_id == next(iter(fakes.page_posts))


def test_a_refused_post_is_posted_again_on_retry(committed, ready, fakes):
    user, storage, article_id = ready
    fakes.page_post_refusals = 1
    failed = run(committed, storage, article_id, user.id)
    assert (failed.status, failed.error) == ("failed", "Facebook từ chối đăng bài này")
    assert post_of(committed, article_id).finish_sent_at is None
    assert run(committed, storage, article_id, user.id).status == "done"
    assert fakes.page_post_calls == 2 and len(fakes.page_posts) == 1


def test_unpublish_deletes_the_post_and_check_closes_one_gone_from_facebook(committed, ready, fakes):
    user, storage, article_id = ready
    run(committed, storage, article_id, user.id)
    post = post_of(committed, article_id)
    assert run(committed, storage, article_id, user.id, "unpublish", post.id).status == "done"
    assert fakes.page_posts == {} and post_of(committed, article_id).status == "deleted"

    with committed() as db:
        db.add(
            Publication(article_id=article_id, platform="facebook", fanpage_id=post.fanpage_id, created_by_id=user.id)
        )
        db.commit()
    run(committed, storage, article_id, user.id)
    with committed() as db:
        live = db.scalar(
            select(Publication).where(Publication.article_id == article_id, Publication.status == "published")
        )
    fakes.page_posts.clear()
    assert run(committed, storage, article_id, user.id, "check", live.id).status == "done"
    with committed() as db:
        assert db.get(Publication, live.id).status == "deleted"


# --- Comment and numbers ---


def live_post(db, user, fakes, minutes_ago=60, **fields) -> Publication:
    pid = db.scalar(select(Fanpage.id).where(Fanpage.page_id == FACEBOOK_PAGE)) or page_id(db, user)
    article = add_article(db, user)
    remote = f"{FACEBOOK_PAGE}_{len(fakes.page_posts) + 100}"
    fakes.page_posts[remote] = {"message": CAPTION, "published": True, "scheduled": None, "photo": None, "edge": "feed"}
    post = Publication(
        article_id=article.id,
        platform="facebook",
        fanpage_id=pid,
        status="published",
        remote_id=remote,
        published_at=ago(minutes_ago),
        created_by_id=user.id,
        **fields,
    )
    db.add(post)
    db.commit()
    return post


def test_the_comment_under_an_article_holds_its_products_links_only(db, me, fakes):
    post = live_post(db, me, fakes, auto_comment=True)
    product = add_product(db, me)
    db.add(ArticleAffiliateProduct(article_id=post.article_id, product_id=product.id))
    db.commit()
    assert post.id in [row.id for row in post_comments.due_posts(db, limit=100)]
    post_comments.write(db, post)
    (comment,) = [row for row in fakes.facebook_comments.values() if row["object"] == post.remote_id]
    assert comment["message"] == f"Gối cao su: {product.url}"


def test_the_numbers_of_an_article_are_its_reach_and_counts_without_views(db, me, fakes):
    post = live_post(db, me, fakes)
    fakes.page_post_numbers[post.remote_id] = {"reach": 320, "shares": 1, "comments": 4, "reactions": 18}
    metrics.measure(db, post)
    row = db.scalar(select(PostMetrics).where(PostMetrics.publication_id == post.id, PostMetrics.window == "latest"))
    assert (row.views, row.reach, row.shares, row.comments, row.reactions) == (None, 320, 1, 4, 18)
    assert row.plays is None and row.retention is None


def test_a_retired_reach_leaves_only_reach_empty(db, me, fakes):
    post = live_post(db, me, fakes)
    fakes.page_post_reach_retired = True
    metrics.measure(db, post)
    row = db.scalar(select(PostMetrics).where(PostMetrics.publication_id == post.id))
    assert (row.reach, row.comments, post.metrics_error) == (None, 6, None)


def test_the_48h_reading_is_kept_and_the_share_rate_waits_for_50_people(db, me, fakes):
    post = live_post(db, me, fakes, minutes_ago=49 * 60)
    fakes.page_post_numbers[post.remote_id] = {"reach": 40, "shares": 2, "comments": 1, "reactions": 3}
    metrics.measure(db, post)
    payload = article_posts.numbers_payload(post, analytics.article_medians(db))
    assert payload["at_48h"]["reach"] == 40
    # 2 shares out of 40 people would read as 5 %: too few people to mean anything.
    assert payload["analysis"]["share_rate"] is None
    assert analytics.article_rate(400, 2) == 0.005


def test_an_article_is_compared_with_its_pages_articles_only_from_five(db, me, fakes, storage):
    posts = [live_post(db, me, fakes, minutes_ago=50 * 60) for _ in range(5)]
    for post, reach in zip(posts, (100, 120, 80, 110, 2000), strict=True):
        db.add(PostMetrics(publication_id=post.id, window="48h", reach=reach, shares=1, measured_at=ago(1)))
    # A reel's views on the same Page do not count.
    video = make_video(db, storage, me, scene_count=1)
    reel = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=posts[0].fanpage_id,
        status="published",
        published_at=ago(3000),
        created_by_id=me.id,
    )
    db.add(reel)
    db.flush()
    db.add(PostMetrics(publication_id=reel.id, window="48h", views=99999, reach=99999, measured_at=ago(1)))
    db.commit()
    by_page = analytics.article_medians(db)
    median = by_page[posts[0].fanpage_id]
    assert (median.views, median.samples) == (110, 5)
    standout = analytics.of_article_post(posts[4], 2000, 1, by_page)
    assert standout["standout"] is True and standout["times_median"] == 18.2
    assert analytics.of_article_post(posts[0], 100, 1, by_page)["standout"] is False
    # Reels' medians leave articles out.
    assert analytics.medians(db)[posts[0].fanpage_id].samples == 1


def test_visitors_comments_under_an_article_name_it_on_binh_luan(an, db, me, fakes):
    post = live_post(db, me, fakes)
    db.add(
        PageComment(
            publication_id=post.id, remote_id="c_1", author_name="Lan", message="Ngủ trưa bao lâu?", created_at=ago(5)
        )
    )
    db.commit()
    (row,) = an.get("/api/comments").json()["comments"]
    assert row["post"]["title"] == "Bài viết: Ngủ đủ giấc quan trọng hơn bạn nghĩ"
    assert (row["post"]["article_id"], row["post"]["video_id"]) == (post.article_id, None)
    assert row["post"]["reel_url"] == f"https://www.facebook.com/{post.remote_id}"
