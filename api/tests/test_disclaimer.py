"""The medical reminder moved from the caption to the last pinned comment (decisions 2026-11-25): cleaning a caption
(no database), the prompt, and the worker writing the reminder at the end of the last comment."""

from conftest import first_topic
from test_pinned_comments import TEXTS, live_article, messages, rows, step

from reels_api import article_posts, articles, disclaimer, slot_comments
from reels_api.models import Article, KnowledgeTopic

NOTE = (
    "(*) Thông tin chỉ mang tính tham khảo, không thay thế lời khuyên y khoa. "
    "Nếu có vấn đề về sức khỏe, bạn hãy hỏi ý kiến bác sĩ để được tư vấn phù hợp nhé."
)
QUESTION = "Món đậu phụ nhà bạn hay làm nhất là gì?"
TAGS = "#dauphu"
BODY = "Đậu phụ giàu đạm thực vật.\nHấp hoặc luộc cho đỡ dầu mỡ."


# --- Cleaning a caption (no database) ---


def test_the_reminder_between_the_body_and_the_question_goes():
    caption = f"Đậu phụ hợp bữa tối\n\n{BODY}\n\n{NOTE}\n\n{QUESTION}"
    assert disclaimer.strip(caption) == f"Đậu phụ hợp bữa tối\n\n{BODY}\n\n{QUESTION}"


def test_a_reminder_at_the_end_goes_too():
    caption = f"Đậu phụ hợp bữa tối\n\n{BODY}\n\n{QUESTION}\n\n{NOTE}"
    assert disclaimer.strip(caption) == f"Đậu phụ hợp bữa tối\n\n{BODY}\n\n{QUESTION}"


def test_a_caption_without_a_reminder_is_unchanged():
    caption = f"Đậu phụ hợp bữa tối\n\n{BODY}\n\n{QUESTION}"
    assert disclaimer.strip(caption) == caption
    assert disclaimer.strip(f"{caption}\n\n\n{QUESTION}") == f"{caption}\n\n\n{QUESTION}"  # nothing removed: as it is


def test_a_sentence_with_tham_khao_that_is_not_a_reminder_stays():
    caption = f"Đậu phụ hợp bữa tối\n\nBạn tham khảo cách làm dưới đây:\n- Hấp 10 phút\n\n{QUESTION}"
    assert disclaimer.strip(caption) == caption


def test_a_reminder_without_the_star_is_known_by_its_words():
    caption = f"Hook\n\n{BODY}\n\nTham khảo, không thay thế tư vấn bác sĩ.\n\n{QUESTION}"
    assert disclaimer.strip(caption) == f"Hook\n\n{BODY}\n\n{QUESTION}"


def test_a_long_paragraph_with_the_words_is_not_taken_for_a_reminder():
    long = "Tham khảo ý kiến bác sĩ là việc nên làm. " * 10
    caption = f"Hook\n\n{long.strip()}\n\n{QUESTION}"
    assert disclaimer.strip(caption) == caption


def test_the_hook_stays_even_with_the_words():
    caption = f"Tham khảo bác sĩ trước khi ăn chay\n\n{BODY}"
    assert disclaimer.strip(caption) == caption


def test_the_caption_is_only_cleaned_for_a_group_with_the_reminder_in_the_comment():
    group = KnowledgeTopic(name="x", medical_disclaimer_enabled=True, medical_disclaimer_position="last_comment")
    caption = f"Hook\n\n{BODY}\n\n{NOTE}\n\n{QUESTION}"
    assert NOTE not in disclaimer.clean_caption(group, caption)
    group.medical_disclaimer_position = "caption"
    assert disclaimer.clean_caption(group, caption) == caption
    group.medical_disclaimer_position, group.medical_disclaimer_enabled = "last_comment", False
    assert disclaimer.clean_caption(group, caption) == caption
    assert disclaimer.clean_caption(None, caption) == caption


def test_the_sentence_goes_after_a_blank_line_and_only_once():
    group = KnowledgeTopic(name="x", medical_disclaimer_enabled=True, medical_disclaimer_position="last_comment")
    joined, own = disclaimer.attach("Ai nên hạn chế.  ", group)
    assert joined == f"Ai nên hạn chế.\n\n{disclaimer.DEFAULT_TEXT}" and not own
    assert disclaimer.attach(joined, group) == (joined, False)  # the member typed it already
    assert disclaimer.attach("Hỏi bác sĩ nhé", None) == ("Hỏi bác sĩ nhé", False)


def test_a_comment_too_long_to_carry_it_gets_it_as_a_comment_of_its_own():
    group = KnowledgeTopic(name="x", medical_disclaimer_enabled=True, medical_disclaimer_position="last_comment")
    long = "a" * (disclaimer.MAX_COMMENT - 10)
    assert disclaimer.attach(long, group) == (long, True)


def test_the_prompt_asks_for_no_reminder_when_it_goes_to_the_comment():
    shown = articles.output_format("kien_thuc", comment_disclaimer=True)
    assert '"note"' not in shown and "app tự đăng câu này dưới bình luận" in shown
    old = articles.output_format("kien_thuc")
    assert '"note"' in old and "tự đăng" not in old


def test_the_check_warns_of_a_reminder_it_does_not_know():
    caption = f"Hook\n\n{BODY}\n\nNgười bệnh nền nên hỏi bác sĩ trước nhé.\n\n{QUESTION}"
    article = type("A", (), {"caption": caption, "hashtags": [], "pinned_comment": "", "kind": "kien_thuc"})()
    warned = articles.checks(article, [], comment_disclaimer=True)["warnings"]
    assert any("còn câu lưu ý y khoa" in item["message"] for item in warned)
    assert not articles.checks(article, [], comment_disclaimer=False)["warnings"]


# --- The worker ---


def with_reminder(db, enabled=True, position="last_comment"):
    group = first_topic(db)
    group.medical_disclaimer_enabled, group.medical_disclaimer_position = enabled, position
    db.commit()
    return group


def run(db, post_id, rounds=8):
    for _ in range(rounds):
        step(db, post_id)


def test_the_last_comment_carries_the_reminder_and_the_count_stays_five(db, me, fakes):
    with_reminder(db)
    post, _ = live_article(db, me, fakes, pin_index=2)
    run(db, post.id)
    sent = messages(fakes, post)
    # The pin first, then the others in order: the last is the fifth text.
    assert sent[:4] == [TEXTS[2], TEXTS[0], TEXTS[1], TEXTS[3]] and len(sent) == 5
    assert sent[4] == f"{TEXTS[4]}\n\n{disclaimer.DEFAULT_TEXT}"
    assert [row.text for row in rows(db, post.id)] == TEXTS  # the stored text never holds the sentence


def test_dragging_a_comment_to_the_end_moves_the_reminder_with_it(db, me, fakes):
    with_reminder(db)
    post, slot = live_article(db, me, fakes)
    slot.pinned_comments = [*slot.pinned_comments[1:], slot.pinned_comments[0]]  # the first one is now last
    db.commit()
    run(db, post.id)
    assert messages(fakes, post)[-1].endswith(disclaimer.DEFAULT_TEXT)
    assert messages(fakes, post)[-1].startswith(TEXTS[0])
    assert sum(disclaimer.DEFAULT_TEXT in text for text in messages(fakes, post)) == 1


def test_a_group_without_the_reminder_writes_the_comments_as_before(db, me, fakes):
    with_reminder(db, enabled=False)
    post, _ = live_article(db, me, fakes)
    run(db, post.id)
    assert messages(fakes, post) == [TEXTS[0], TEXTS[1], TEXTS[2], TEXTS[3], TEXTS[4]]


def test_the_position_caption_brings_back_the_old_way(db, me, fakes):
    with_reminder(db, position="caption")
    post, _ = live_article(db, me, fakes)
    run(db, post.id)
    assert messages(fakes, post) == TEXTS


def test_a_comment_that_already_has_the_reminder_is_not_given_a_second(db, me, fakes):
    with_reminder(db)
    typed = [{"type": "luu_y", "text": f"{TEXTS[4]}\n\n{NOTE}"}]
    post, _ = live_article(db, me, fakes, pinned=typed)
    run(db, post.id)
    assert messages(fakes, post) == [f"{TEXTS[4]}\n\n{NOTE}"]


def test_an_article_without_comments_gets_one_comment_with_the_reminder(db, me, fakes):
    with_reminder(db)
    post, _ = live_article(db, me, fakes, pinned=[])
    assert post.id in slot_comments.due_posts(db)
    run(db, post.id)
    assert messages(fakes, post) == [disclaimer.DEFAULT_TEXT]
    only = rows(db, post.id)
    assert len(only) == 1 and only[0].type == slot_comments.REMINDER_TYPE and only[0].text == ""
    assert slot_comments.post_payload(db, post)["items"][0]["text"] == disclaimer.DEFAULT_TEXT


def test_with_the_switch_off_the_reminder_is_still_a_comment_of_its_own(db, me, fakes):
    with_reminder(db)
    post, _ = live_article(db, me, fakes, enabled=False)
    assert post.id in slot_comments.due_posts(db)
    run(db, post.id)
    assert messages(fakes, post) == [disclaimer.DEFAULT_TEXT]


def test_a_comment_too_long_is_followed_by_the_reminder_as_a_comment_of_its_own(db, me, fakes):
    with_reminder(db)
    long = "b" * (disclaimer.MAX_COMMENT - 10)
    post, _ = live_article(db, me, fakes, pinned=[{"type": "luu_y", "text": long}])
    run(db, post.id)
    assert messages(fakes, post) == [long, disclaimer.DEFAULT_TEXT]


def test_a_changed_sentence_is_read_from_the_group_when_written(db, me, fakes):
    group = with_reminder(db)
    group.medical_disclaimer_text = "Nhớ hỏi bác sĩ nhé."
    db.commit()
    post, _ = live_article(db, me, fakes, pinned=[{"type": "luu_y", "text": TEXTS[4]}])
    run(db, post.id)
    assert messages(fakes, post) == [f"{TEXTS[4]}\n\nNhớ hỏi bác sĩ nhé."]


def test_the_preview_shows_the_comments_as_they_will_be_written(db, me, fakes):
    with_reminder(db)
    post, slot = live_article(db, me, fakes, pin_index=2)
    article = db.get(Article, slot.article_id)
    planned = slot_comments.planned_texts(db, article)
    assert planned == [TEXTS[2], TEXTS[0], TEXTS[1], TEXTS[3], f"{TEXTS[4]}\n\n{disclaimer.DEFAULT_TEXT}"]
    article.caption = f"Hook\n\n{BODY}\n\n{NOTE}\n\n{QUESTION}"
    shown = article_posts.post_text(db, article)
    assert NOTE not in shown and shown.endswith(QUESTION)
    assert article.caption.count(NOTE) == 1  # the caption itself is not changed
    assert article_posts.payload(db, article)["disclaimer"]["text"] == disclaimer.DEFAULT_TEXT
