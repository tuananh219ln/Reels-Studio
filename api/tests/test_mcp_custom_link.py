"""The assistant's side of Shopee's Custom Link: the links to convert, a preview of the result file, then the import."""

from conftest import first_topic
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import AffiliateProduct, Fanpage, KnowledgeTopic

RESULT = (
    "﻿Liên kết gốc,Sub_id1,Sub_id2,Sub_id3,Sub_id4,Sub_id5,Liên kết chuyển đổi,Lí do thất bại\n"
    "https://shopee.vn/product/1/1,p1,,,,,https://s.shopee.vn/AAA,\n"
    "https://shopee.vn/product/1/2,p1,,,,,,Liên kết không hợp lệ\n"
)


def product(db, user, topic, n, **fields) -> AffiliateProduct:
    row = AffiliateProduct(
        knowledge_topic_id=topic.id,
        name=f"Món {n}",
        page_url=f"https://shopee.vn/product/1/{n}",
        shop_name="Shop",
        shop_type="mall",
        rating=4.8,
        sold=500,
        price=100000,
        commission_rate=10,
        status="approved",
        created_by_id=user.id,
        **fields,
    )
    db.add(row)
    db.commit()
    return row


def page(db, topic, name="Page A") -> Fanpage:
    row = Fanpage(page_id=f"fb-{name}", name=name, token_encrypted="x", token_tail="x", knowledge_topic_id=topic.id)
    db.add(row)
    db.commit()
    return row


def test_the_links_to_convert_come_with_the_pages_sub_id(mcp_client, db):
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    topic = first_topic(db)
    target = page(db, topic)
    product(db, user, topic, 1)
    product(db, user, topic, 2, url="https://s.shopee.vn/already")
    listed = call(mcp_client, token, "list_custom_link_products", knowledge_topic_id=topic.id)
    assert not listed.get("isError"), listed
    content = payload(listed)
    assert content["sub_id1"] == f"p{target.id}"
    assert content["links"] == ["https://shopee.vn/product/1/1"]
    again = payload(
        call(mcp_client, token, "list_custom_link_products", knowledge_topic_id=topic.id, include_linked=True)
    )
    assert len(again["links"]) == 2


def test_a_group_with_two_pages_asks_which(mcp_client, db):
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    topic = KnowledgeTopic(name="Hai Page", created_by_id=user.id)
    db.add(topic)
    db.commit()
    page(db, topic, "A")
    chosen = page(db, topic, "B")
    product(db, user, topic, 1)
    refused = call(mcp_client, token, "list_custom_link_products", knowledge_topic_id=topic.id)
    assert refused["isError"]
    assert "chọn Page" in refused["content"][0]["text"]
    listed = call(mcp_client, token, "list_custom_link_products", knowledge_topic_id=topic.id, fanpage_id=chosen.id)
    assert payload(listed)["sub_id1"] == f"p{chosen.id}"


def test_the_preview_writes_nothing_and_the_import_puts_the_link_on(mcp_client, db):
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    topic = first_topic(db)
    first = product(db, user, topic, 1)
    product(db, user, topic, 2)
    shown = payload(call(mcp_client, token, "preview_custom_link_import", knowledge_topic_id=topic.id, csv_text=RESULT))
    assert (shown["ok"], shown["errors"], shown["others"]) == (1, 1, 0)
    assert "Liên kết không hợp lệ" in shown["rows"][1]["message"]
    db.refresh(first)
    assert first.url is None

    done = call(mcp_client, token, "import_custom_link_result", knowledge_topic_id=topic.id, csv_text=RESULT)
    assert not done.get("isError"), done
    assert payload(done)["linked"] == 1
    db.refresh(first)
    assert first.url == "https://s.shopee.vn/AAA"
