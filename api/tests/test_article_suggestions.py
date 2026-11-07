"""An article's pinned comment and Shopee product suggestions ("Bài viết"), as a video's."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from test_affiliate_accounts import PRODUCTS, product, shopee_account

from reels_api import affiliate_rounds, fanpages, post_comments
from reels_api.models import AffiliateProduct, Article, ArticleAffiliateProduct, Publication


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_article(db, user, **fields) -> Article:
    article = Article(
        knowledge_topic_id=first_topic(db).id,
        kind="meo",
        topic="Ngâm chân",
        caption="Ngâm chân nước gừng\n\nNội dung",
        created_by_id=user.id,
        **fields,
    )
    db.add(article)
    db.commit()
    return article


def live_post(db, user, fakes, article: Article) -> Publication:
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
    db.flush()
    remote = f"{FACEBOOK_PAGE}_77"
    fakes.page_posts[remote] = {"message": "x", "published": True, "scheduled": None, "photo": None, "edge": "feed"}
    post = Publication(
        article_id=article.id,
        platform="facebook",
        fanpage_id=page.id,
        status="published",
        remote_id=remote,
        published_at=datetime.now(UTC) - timedelta(minutes=10),
        auto_comment=True,
        created_by_id=user.id,
    )
    db.add(post)
    db.commit()
    return post


def test_the_comment_under_an_article_is_its_pinned_comment_then_the_links(db, me, fakes):
    article = add_article(db, me, pinned_comment="Bạn ngâm chân mấy lần một tuần?")
    post = live_post(db, me, fakes, article)
    row = product(db, me, url="https://s.shopee.vn/goi")
    db.add(ArticleAffiliateProduct(article_id=article.id, product_id=row.id))
    db.commit()
    post_comments.write(db, post)
    (comment,) = [item for item in fakes.facebook_comments.values() if item["object"] == post.remote_id]
    assert comment["message"] == f"Bạn ngâm chân mấy lần một tuần?\n{row.name}: {row.url}"


def test_a_pinned_comment_alone_makes_the_post_write_a_comment(an, db, me):
    article = add_article(db, me, pinned_comment="Kể mình nghe nhé!")
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    db.commit()
    saved = an.post(f"/api/articles/{article.id}/publish", json={"fanpage_id": page.id}).json()
    assert saved["posts"][0]["comment"]["auto"] is True


def test_editing_the_pinned_comment_edits_the_comment_already_written(an, db, me, fakes):
    article = add_article(db, me, pinned_comment="Cũ")
    post = live_post(db, me, fakes, article)
    post.comment_id = "c-1"
    db.commit()
    an.patch(f"/api/articles/{article.id}", json={"pinned_comment": "Mới"})
    db.expire_all()
    assert db.get(Publication, post.id).comment_requested_at is not None


def test_asking_for_suggestions_needs_ideas_and_my_own_shopee_account(an, db, me):
    article = add_article(db, me)
    path = f"{PRODUCTS}/articles/{article.id}/suggestions"
    assert "Gợi ý sản phẩm" in an.post(path).json()["message"]
    article.affiliates = ["Vừng đen"]
    db.commit()
    assert "Tài khoản affiliate" in an.post(path).json()["message"]
    shopee_account(an)
    assert an.post(path).json()["state"] == "pending"


def test_the_worker_searches_shopee_for_an_articles_ideas(an, db, me, fakes):
    shopee_account(an)
    article = add_article(db, me, affiliates=["Vừng đen"])
    an.post(f"{PRODUCTS}/articles/{article.id}/suggestions")
    db.expire_all()
    affiliate_rounds.suggest(db, db.get(Article, article.id))
    (group,) = an.get(f"{PRODUCTS}/articles/{article.id}/suggestions").json()["keywords"]
    assert [row["name"] for row in group["products"]] == ["Vừng đen loại 1", "Vừng đen loại 2"]
    assert db.get(Article, article.id).suggest_requested_at is None


def test_the_article_says_when_its_search_finished(an, db, me, fakes):
    # The page reloads the suggestions when this changes: a search that ends before the page sees it pending still
    # shows up, because the time it finished is new.
    shopee_account(an)
    article = add_article(db, me, affiliates=["Vừng đen"])
    assert an.get(f"/api/articles/{article.id}").json()["suggest"] == {"state": "idle", "error": None, "at": None}
    an.post(f"{PRODUCTS}/articles/{article.id}/suggestions")
    db.expire_all()
    affiliate_rounds.suggest(db, db.get(Article, article.id))
    suggest = an.get(f"/api/articles/{article.id}").json()["suggest"]
    assert (suggest["state"], suggest["error"]) == ("idle", None) and suggest["at"] is not None


def test_a_new_caption_asks_for_suggestions_when_its_writer_has_an_account(an, db, me):
    article = add_article(db, me, affiliates=["Vừng đen"])
    shopee_account(an)
    affiliate_rounds.ask_after_script(db, article, me.id)
    assert article.suggest_requested_at is not None and article.suggest_by_id == me.id


def test_choosing_approves_attaches_and_stops_at_two(an, db, me):
    article = add_article(db, me)
    rows = [product(db, me, name=f"Gối {n}", status="draft", shopee_item_id=n) for n in (1, 2, 3)]
    path = f"{PRODUCTS}/articles/{article.id}/choose"
    for row in rows[:2]:
        assert an.post(path, json={"product_id": row.id}).status_code == 200
    db.expire_all()
    assert db.get(AffiliateProduct, rows[0].id).status == "approved"
    refused = an.post(path, json={"product_id": rows[2].id})
    assert (refused.status_code, refused.json()["code"]) == (409, "too_many_products")
    attached = db.scalars(
        select(ArticleAffiliateProduct.product_id).where(ArticleAffiliateProduct.article_id == article.id)
    )
    assert sorted(attached) == sorted(row.id for row in rows[:2])


def test_a_pasted_link_is_listed_for_the_article(an, db, me):
    article = add_article(db, me)
    result = an.post(f"{PRODUCTS}/articles/{article.id}/links", json={"links": ["https://s.shopee.vn/abc"]}).json()
    (group,) = result["keywords"]
    assert group["pasted"] is True and len(group["products"]) == 1
