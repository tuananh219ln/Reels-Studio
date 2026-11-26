"""The Telegram bot's commands (telegram_commands.py, docs/decisions/2026-11-26-telegram-commands.md): the same in the
team's group and in a private chat, a member's own work always answered privately, the queue after "Duyệt", the
reason after "Bỏ", and the group's daily summary. None of them calls an AI."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_user, make_video
from sqlalchemy import select
from test_telegram import CHAT, TOKEN, link, press, private, rendered, texts, update

from reels_api import fanpages, telegram, telegram_commands
from reels_api.analytics import VIETNAM
from reels_api.models import AppSetting, Job, PageQueueItem, PostMetrics, Publication, VideoEvent

GROUP = -100123


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def bot(fakes, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(telegram, "_usernames", {})
    monkeypatch.setattr(telegram, "_webhooks", set())
    return fakes


def in_group(text: str, sender=CHAT) -> dict:
    return {"message": {"chat": {"id": GROUP, "type": "group"}, "from": {"id": sender}, "text": text}}


def sent_to(bot, chat) -> list[str]:
    return [fields["text"] for fields in bot.telegram_sent("sendMessage") if fields["chat_id"] == chat]


def test_a_personal_command_in_the_group_is_answered_privately(app, db, me, bot, storage):
    link(db, me)
    video = rendered(db, storage, me)
    update(app, in_group("/cho_duyet@reels_test_bot"))
    assert sent_to(bot, GROUP) == ["📩 Đã gửi riêng cho Nguyễn Văn An."]
    (mine,) = bot.telegram_sent("sendMessage")[:1]
    assert mine["chat_id"] == CHAT and "1 video của bạn đang chờ duyệt" in mine["text"]
    assert mine["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"rv:{video.id}"
    # Its button sends the MP4 with Duyệt / Bỏ, as the notice does.
    update(app, press(f"rv:{video.id}"))
    assert bot.telegram_sent("sendVideo")[0]["chat_id"] == str(CHAT)


def test_someone_not_linked_is_told_how_to_link_and_nothing_personal_is_said(app, db, me, bot, storage):
    rendered(db, storage, me)
    update(app, in_group("/loi", sender=999))
    assert sent_to(bot, GROUP) == [telegram_commands.NOT_LINKED]


def test_the_same_commands_work_in_a_private_chat(app, db, me, bot, storage):
    link(db, me)
    video = make_video(db, storage, me, scene_count=1)
    job = Job(video_id=video.id, kind="render", status="failed", created_by_id=me.id, error="Hết dung lượng")
    db.add(job)
    db.flush()
    job.finished_at = datetime.now(UTC)
    db.commit()
    update(app, private("/loi"))
    assert "Render</a>" in texts(bot)[-1] and "Hết dung lượng" in texts(bot)[-1]
    update(app, private("/hom_nay"))
    assert "Hôm nay" in texts(bot)[-1] and "Không có bài nào hẹn đăng hôm nay" in texts(bot)[-1]
    update(app, private("/cho_duyet"))
    assert texts(bot)[-1] == "✅ Không có video nào của bạn đang chờ duyệt."


def test_team_wide_commands_are_answered_where_asked(app, db, me, bot, storage):
    rendered(db, storage, me)
    update(app, in_group("/tong_quan@reels_test_bot", sender=999))
    assert "Đang chờ duyệt: 1 video" in sent_to(bot, GROUP)[-1]
    assert "Nguyễn" not in sent_to(bot, GROUP)[-1]
    update(app, in_group("/huongdan telegram", sender=999))
    answer = sent_to(bot, GROUP)[-1]
    assert "Hướng dẫn: Thông báo Telegram" in answer and "/guides?guide=telegram" in answer
    update(app, in_group("/huongdan khongcotukhoanay", sender=999))
    assert "Không tìm thấy" in sent_to(bot, GROUP)[-1]
    bot.changelog = {
        "entries": [
            {"title": "Tin riêng", "summary": "Bot nhắn riêng.", "kind": "feature", "merged_at": "2026-11-26T10:00:00Z"}
        ]
    }
    update(app, in_group("/moi", sender=999))
    assert "<b>Tin riêng</b> (Tính năng mới)" in sent_to(bot, GROUP)[-1]
    update(app, in_group("/help", sender=999))
    assert "/cho_duyet" in sent_to(bot, GROUP)[-1]


def test_after_duyet_the_video_goes_to_a_pages_queue_with_one_press(app, db, me, bot, storage):
    link(db, me)
    video = rendered(db, storage, me)
    page = fanpages.save(db, "pg1", "Trang Dưỡng Sinh", "token-cua-page", me.id)
    page.knowledge_topic_id = video.knowledge_topic_id
    db.commit()
    signature = video.rendered_signature[: telegram.SIGNATURE_CHARS]
    update(app, press(f"aq:{video.id}:{signature}"))
    offer = bot.telegram_sent("sendMessage")[-1]
    assert offer["text"].startswith("✅ Đã duyệt") and "Thêm vào hàng chờ" in offer["text"]
    data = offer["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert data == f"qa:{video.id}:{page.id}"
    update(app, press(data))
    item = db.scalar(select(PageQueueItem).where(PageQueueItem.video_id == video.id))
    assert item.fanpage_id == page.id and item.added_by_id == me.id
    assert "Đã thêm vào hàng chờ của <b>Trang Dưỡng Sinh</b>" in texts(bot)[-1]
    update(app, press(data))
    assert "đã ở trong một hàng chờ" in bot.telegram_sent("answerCallbackQuery")[-1]["text"]


def test_after_bo_the_reason_typed_back_is_kept(app, db, me, bot, storage):
    link(db, me)
    video = rendered(db, storage, me)
    update(app, press(f"rj:{video.id}:{video.rendered_signature[: telegram.SIGNATURE_CHARS]}"))
    asked = bot.telegram_sent("sendMessage")[-1]
    assert f"(#v{video.id})" in asked["text"] and asked["reply_markup"]["force_reply"] is True
    reply = private("Ảnh cảnh 2 bị mờ")
    reply["message"]["reply_to_message"] = {"text": asked["text"], "from": {"id": 4242, "is_bot": True}}
    update(app, reply)
    event = db.scalar(select(VideoEvent).where(VideoEvent.video_id == video.id, VideoEvent.type == "rejected"))
    db.refresh(event)
    assert event.payload["reason"] == "Ảnh cảnh 2 bị mờ"
    assert texts(bot)[-1] == "📝 Đã ghi lý do bỏ video."


def test_the_group_hears_the_days_summary_once_in_the_evening(db, me, bot, storage, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(GROUP))
    video = make_video(db, storage, me, scene_count=1)
    video.name = "Canxi cho xương"
    post = Publication(
        video_id=video.id,
        platform="facebook",
        status="published",
        published_at=datetime.now(UTC),
        created_by_id=me.id,
    )
    db.add(post)
    db.flush()
    db.add(PostMetrics(publication_id=post.id, window="latest", views=12345, measured_at=datetime.now(UTC)))
    db.commit()
    today = datetime.now(VIETNAM).date()
    evening = datetime(today.year, today.month, today.day, 21, 30, tzinfo=VIETNAM)
    assert telegram_commands.group_summary(db, evening - timedelta(hours=2)) is False
    assert telegram_commands.group_summary(db, evening) is True
    assert telegram_commands.group_summary(db, evening + timedelta(minutes=20)) is False
    (summary,) = sent_to(bot, GROUP)
    assert "Tổng kết ngày" in summary and "<b>Canxi cho xương</b>" in summary and "12,345 view" in summary
    assert db.get(AppSetting, telegram_commands.SUMMARY_KEY).value == today.isoformat()


def test_no_group_id_no_summary(db, bot):
    later = datetime.now(VIETNAM).replace(hour=22)
    assert telegram_commands.group_summary(db, later) is False
    assert bot.telegram_calls == []
