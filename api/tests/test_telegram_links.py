"""Shopee links sent to the bot in a private chat (telegram_links.py, docs/decisions/2026-11-28-telegram-links.md)."""

import pytest
from conftest import first_topic, make_user
from sqlalchemy import select
from test_telegram import TOKEN, link, private, texts, update

from reels_api import telegram, telegram_commands
from reels_api.models import AffiliateProduct, KnowledgeTopic

PAGE = "https://shopee.vn/product/938402459/28818204493"
SHORT = "https://s.shopee.vn/gRyl9IBkJ"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def bot(fakes, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(telegram, "_usernames", {})
    monkeypatch.setattr(telegram, "_webhooks", set())
    return fakes


def mine(db, user) -> list[AffiliateProduct]:
    return list(db.scalars(select(AffiliateProduct).where(AffiliateProduct.created_by_id == user.id)))


def test_links_become_the_members_products(app, db, me, bot):
    link(db, me)
    update(app, private(f"Mấy món mới\n{PAGE}\n{SHORT}, xong"))
    rows = {row.page_url or row.url: row for row in mine(db, me)}
    # A product page keeps its address as the page; a short link is the member's own link, as on the web.
    assert set(rows) == {PAGE, SHORT}
    assert rows[PAGE].page_url == PAGE and rows[PAGE].url is None and rows[PAGE].status == "draft"
    assert rows[SHORT].url == SHORT and rows[SHORT].page_url is None
    assert all(row.knowledge_topic_id == first_topic(db).id for row in rows.values())
    assert "Đã thêm 2 sản phẩm" in texts(bot)[-1]


def test_a_link_already_listed_is_skipped(app, db, me, bot):
    link(db, me)
    update(app, private(PAGE))
    update(app, private(f"{PAGE} {SHORT}"))
    assert len(mine(db, me)) == 2
    assert "Đã thêm 1 sản phẩm" in texts(bot)[-1] and "1 link đã có sẵn" in texts(bot)[-1]


def test_with_several_groups_the_first_line_names_one(app, db, me, bot):
    link(db, me)
    other = KnowledgeTopic(name="Món ăn nhanh", created_by_id=me.id)
    db.add(other)
    db.commit()
    update(app, private(PAGE))
    assert mine(db, me) == []
    assert "Bạn có nhiều nhóm" in texts(bot)[-1] and "Món ăn nhanh" in texts(bot)[-1]
    update(app, private(f"mon an nhanh\n{PAGE}"))
    (row,) = mine(db, me)
    assert row.knowledge_topic_id == other.id
    assert "nhóm “Món ăn nhanh”" in texts(bot)[-1]


def test_someone_not_linked_is_told_how_to_link(app, db, me, bot):
    update(app, private(PAGE))
    assert texts(bot) == [telegram_commands.NOT_LINKED]
    assert mine(db, me) == []


def test_only_fifty_links_a_message(app, db, me, bot):
    link(db, me)
    update(app, private("\n".join(f"https://shopee.vn/product/1/{n}" for n in range(1, 53))))
    assert len(mine(db, me)) == 50
    assert "còn 2 link chưa thêm" in texts(bot)[-1]


def test_other_links_and_plain_text_are_not_taken(app, db, me, bot):
    link(db, me)
    update(app, private("xem https://example.com/product/1/2 nhé"))
    update(app, private("xin chào"))
    assert mine(db, me) == []
    assert all("Đã thêm" not in text for text in texts(bot))
