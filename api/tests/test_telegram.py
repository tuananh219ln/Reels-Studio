"""Private Telegram messages to each member (telegram.py, docs/decisions/2026-11-26-telegram-private.md): linking a
chat through the bot's /start link, what each member is told about their own work, the Duyệt / Bỏ buttons, and the
bot staying quiet without a token."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import client_for, login, make_user, make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client  # noqa: F401  (mcp_client is a fixture)
from test_publish import add_mp4

from reels_api import fanpages, review, telegram
from reels_api.analytics import VIETNAM
from reels_api.models import Job, Publication, TelegramNotice, Video, VideoEvent

TOKEN = "123456:test-telegram-token"
CHAT = 7001
OTHER_CHAT = 7002
URL = "/api/telegram"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def bot(fakes, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(telegram, "_usernames", {})
    monkeypatch.setattr(telegram, "_webhooks", set())
    return fakes


def ago(**delta) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


def link(db, user, chat=CHAT, muted=("reminder",)):
    """Linked an hour ago: what happened since is told, what happened before is not. The morning reminder is muted
    unless a test is about it, so the time of day the tests run at does not matter."""
    user.telegram_chat_id, user.telegram_username, user.telegram_linked_at = chat, "an", ago(hours=1)
    user.telegram_muted = list(muted)
    db.commit()
    return user


def update(app, body: dict, secret: str | None = None):
    # Telegram sends no Origin: the webhook is let through the CSRF guard by its path, then checked by its secret.
    plain = client_for(app)
    plain.headers.pop("Origin")
    headers = {"X-Telegram-Bot-Api-Secret-Token": telegram.webhook_secret() if secret is None else secret}
    return plain.post(f"{URL}/webhook", json=body, headers=headers)


def private(text: str, chat=CHAT) -> dict:
    return {"message": {"chat": {"id": chat, "type": "private"}, "from": {"id": chat, "username": "an"}, "text": text}}


def press(data: str, chat=CHAT, message_id=55) -> dict:
    return {
        "callback_query": {
            "id": "q1",
            "from": {"id": chat},
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat, "type": "private"}},
        }
    }


def rendered(db, storage, user) -> Video:
    video = make_video(db, storage, user, scene_count=1)
    add_mp4(db, storage, video, approved=False)
    review.after_render(db, video.id)
    return video


def notices(db, user) -> list[TelegramNotice]:
    return list(db.scalars(select(TelegramNotice).where(TelegramNotice.user_id == user.id).order_by(TelegramNotice.id)))


def texts(bot) -> list[str]:
    return [fields["text"] for fields in bot.telegram_sent("sendMessage")]


# --- Without a token ---


def test_without_a_token_the_page_says_the_bot_is_off_and_nothing_is_collected(an, db, me, fakes, storage):
    answer = an.get(URL).json()
    assert answer["configured"] is False and answer["linked"] is False
    assert [kind["key"] for kind in answer["kinds"]] == ["review", "failed", "connection", "reminder", "muse"]
    refused = an.post(f"{URL}/link")
    assert (refused.status_code, refused.json()["code"]) == (409, "telegram_off")
    link(db, me)
    rendered(db, storage, me)
    telegram.run_round(None)  # returns at once: no factory is even opened
    assert fakes.telegram_calls == []


# --- Linking ---


def test_a_member_links_their_chat_through_the_bots_start_link(an, app, db, me, bot):
    url = an.post(f"{URL}/link").json()["url"]
    assert url.startswith("https://t.me/reels_test_bot?start=")
    hook = bot.telegram_sent("setWebhook")[0]
    assert hook["url"] == "http://localhost:3000/api/telegram/webhook"
    assert hook["secret_token"] == telegram.webhook_secret()

    assert update(app, private(f"/start {url.split('=')[1]}")).status_code == 200
    db.refresh(me)
    assert (me.telegram_chat_id, me.telegram_username) == (CHAT, "an")
    assert me.telegram_link_code_hash is None
    assert "Đã kết nối với tài khoản <b>Nguyễn Văn An</b>" in texts(bot)[-1]
    assert an.get(URL).json()["linked"] is True


def test_an_old_or_wrong_code_links_nothing(an, app, db, me, bot):
    code = an.post(f"{URL}/link").json()["url"].split("=")[1]
    me.telegram_link_expires_at = ago(minutes=1)
    db.commit()
    update(app, private(f"/start {code}"))
    update(app, private("/start khong-dung"))
    db.refresh(me)
    assert me.telegram_chat_id is None
    assert all("hết hạn hoặc không đúng" in text for text in texts(bot))


def test_the_webhook_refuses_anyone_without_the_secret(app, bot):
    assert update(app, private("/chatid"), secret="").status_code == 403
    assert update(app, private("/chatid"), secret="doan-bua").status_code == 403
    assert bot.telegram_calls == []


def test_one_chat_belongs_to_one_member(an, app, db, me, bot):
    other = link(db, make_user(db, email="binh@doi.vn", name="Bình"))
    code = an.post(f"{URL}/link").json()["url"].split("=")[1]
    update(app, private(f"/start {code}"))
    db.refresh(other)
    db.refresh(me)
    assert (me.telegram_chat_id, other.telegram_chat_id) == (CHAT, None)


def test_stop_and_the_settings_page_unlink(an, app, db, me, bot):
    link(db, me)
    update(app, private("/stop"))
    db.refresh(me)
    assert me.telegram_chat_id is None
    link(db, me)
    assert an.delete(f"{URL}/link").json()["linked"] is False
    assert "Đã ngắt kết nối" in texts(bot)[-1]


def test_in_a_group_the_bot_answers_its_commands_only(app, bot):
    group = {"chat": {"id": -100123, "type": "supergroup"}, "from": {"id": CHAT}}
    update(app, {"message": {**group, "text": "chào bot"}})
    assert bot.telegram_calls == []
    update(app, {"message": {**group, "text": "/chatid@reels_test_bot"}})
    assert texts(bot) == ["Chat id: <code>-100123</code>"]
    # /start in a group links nobody (a link code only works in a private chat): the commands are listed instead.
    update(app, {"message": {**group, "text": "/start abc"}})
    assert texts(bot)[-1].startswith("<b>Lệnh của bot Reels Studio</b>")


def test_a_test_message_and_the_muted_kinds(an, db, me, bot):
    assert an.post(f"{URL}/test").json()["code"] == "telegram_not_linked"
    link(db, me)
    assert an.post(f"{URL}/test").status_code == 200
    assert "Tin thử" in texts(bot)[-1]
    assert an.put(f"{URL}/muted", json={"muted": ["reminder", "khong-co"]}).json()["muted"] == ["reminder"]


# --- A video waiting for review ---


def test_the_maker_gets_their_video_with_buttons_once(db, me, bot, storage):
    link(db, me)
    video = rendered(db, storage, me)
    other = make_user(db, email="binh@doi.vn", name="Bình")
    link(db, other, chat=OTHER_CHAT)
    assert telegram.collect(db) == 1
    assert telegram.collect(db) == 0
    assert telegram.deliver(db, storage) == 1
    sent = bot.telegram_sent("sendVideo")
    assert len(sent) == 1 and sent[0]["chat_id"] == str(CHAT) and sent[0]["_file"] == len(b"mp4 bytes")
    assert "Video chờ bạn duyệt" in sent[0]["caption"] and "mục cần xem" in sent[0]["caption"]
    signature = video.rendered_signature[: telegram.SIGNATURE_CHARS]
    assert [button["callback_data"] for button in sent[0]["reply_markup"]["inline_keyboard"][0]] == [
        f"ap:{video.id}:{signature}",
        f"rj:{video.id}:{signature}",
    ]
    assert telegram.deliver(db, storage) == 0


def test_a_video_approved_by_tu_duyet_or_made_before_linking_is_not_told(db, me, bot, storage):
    video = rendered(db, storage, me)
    link(db, me)
    me.telegram_linked_at = datetime.now(UTC) + timedelta(seconds=5)
    db.commit()
    assert telegram.collect(db) == 0
    link(db, me)
    video.review_status = "approved"
    db.commit()
    assert telegram.collect(db) == 0


def test_approving_from_telegram_asks_to_acknowledge_the_warnings(app, db, me, bot, storage):
    link(db, me)
    video = rendered(db, storage, me)
    signature = video.rendered_signature[: telegram.SIGNATURE_CHARS]
    update(app, press(f"ap:{video.id}:{signature}"))
    db.refresh(video)
    assert video.review_status == "pending_review"
    ask = bot.telegram_sent("sendMessage")[-1]
    assert "Vẫn duyệt" in ask["text"]
    assert ask["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"aq:{video.id}:{signature}"

    update(app, press(f"aq:{video.id}:{signature}"))
    db.refresh(video)
    assert (video.review_status, video.approved_via, video.approved_by_id) == ("approved", "telegram", me.id)
    assert bot.telegram_sent("editMessageReplyMarkup")[0]["message_id"] == 55
    assert texts(bot)[-1].startswith("✅ Đã duyệt")
    event = db.scalars(select(VideoEvent).where(VideoEvent.video_id == video.id).order_by(VideoEvent.id.desc())).first()
    assert (event.type, event.channel) == ("approved", "telegram")


def test_rejecting_from_telegram(app, db, me, bot, storage):
    link(db, me)
    video = rendered(db, storage, me)
    update(app, press(f"rj:{video.id}:{video.rendered_signature[: telegram.SIGNATURE_CHARS]}"))
    db.refresh(video)
    assert (video.review_status, texts(bot)[-1].startswith("❌ Đã bỏ video")) == ("rejected", True)


def test_a_button_of_an_older_mp4_or_a_stranger_changes_nothing(app, db, me, bot, storage):
    link(db, me)
    video = rendered(db, storage, me)
    update(app, press(f"aq:{video.id}:cu-roi"))
    update(app, press(f"aq:{video.id}:{video.rendered_signature[: telegram.SIGNATURE_CHARS]}", chat=OTHER_CHAT))
    db.refresh(video)
    assert video.review_status == "pending_review"
    answers = bot.telegram_sent("answerCallbackQuery")
    assert "bản render mới" in answers[0]["text"] and "chưa kết nối" in answers[1]["text"]


# --- Failures, connections, reminders ---


def test_a_failed_job_is_told_to_whoever_queued_it_unless_it_was_tried_again(db, me, bot, storage):
    link(db, me)
    video = make_video(db, storage, me, scene_count=1)
    failed = Job(video_id=video.id, kind="render", status="failed", created_by_id=me.id, error="Hết dung lượng")
    retried = Job(video_id=video.id, kind="publish", status="failed", created_by_id=me.id, error="x")
    db.add_all([failed, retried])
    db.flush()
    failed.finished_at = retried.finished_at = datetime.now(UTC)
    db.add(Job(video_id=video.id, kind="publish", status="done", created_by_id=me.id, retry_of_id=retried.id))
    db.commit()
    assert telegram.collect(db) == 1
    (notice,) = notices(db, me)
    assert notice.key == f"job:{failed.id}" and "Render không thành công" in notice.text
    assert "Hết dung lượng" in notice.text and notice.link == f"/videos/{video.id}"
    telegram.deliver(db, storage)
    assert texts(bot)[-1].endswith(f'<a href="http://localhost:3000/videos/{video.id}">Mở trong Reels Studio</a>')


def test_a_broken_page_is_told_to_its_owner_once_per_time_it_breaks(db, me, bot, storage):
    link(db, me)
    page = fanpages.save(db, "pg1", "Trang Dưỡng Sinh", "token-cua-page", me.id)
    page.check_error = "Token hết hạn"
    db.commit()
    assert telegram.collect(db) == 1
    telegram.deliver(db, storage)
    assert telegram.collect(db) == 0
    assert "Fanpage Trang Dưỡng Sinh mất kết nối" in texts(bot)[-1]
    page.check_error = None
    db.commit()
    telegram.collect(db)
    page.check_error = "Token hết hạn"
    db.commit()
    assert telegram.collect(db) == 1


def test_the_morning_reminder(db, me, bot, storage):
    link(db, me, muted=["review"])
    rendered(db, storage, me)
    page = fanpages.save(db, "pg1", "Trang Dưỡng Sinh", "token-cua-page", me.id)
    page.post_times = ["08:00", "20:00"]
    db.commit()
    today = datetime.now(VIETNAM).date()
    early = datetime(today.year, today.month, today.day, 7, 0, tzinfo=VIETNAM)
    morning = early + timedelta(hours=2)
    # Scheduled after the reminder's own time, not after the clock's: from midnight to 6 AM Vietnam time "now + 3 h"
    # fell before 9 AM and the post no longer counted.
    db.add(
        Publication(
            video_id=make_video(db, storage, me).id,
            platform="facebook",
            fanpage_id=page.id,
            status="scheduled",
            scheduled_at=morning + timedelta(hours=3),
            created_by_id=me.id,
        )
    )
    db.commit()
    assert telegram.collect(db, early) == 0
    assert telegram.collect(db, morning) == 1
    assert telegram.collect(db, morning + timedelta(hours=3)) == 0
    (notice,) = notices(db, me)
    assert "1 video của bạn đang chờ duyệt" in notice.text
    assert "Page Trang Dưỡng Sinh chỉ còn 1 video" in notice.text


def test_a_member_who_blocked_the_bot_is_unlinked(db, me, bot, storage):
    link(db, me)
    bot.telegram_blocked.add(CHAT)
    rendered(db, storage, me)
    telegram.collect(db)
    assert telegram.deliver(db, storage) == 0
    db.refresh(me)
    assert me.telegram_chat_id is None
    assert notices(db, me)[0].sent_at is not None


# --- Muse ---


def test_muse_messages_the_member_privately(mcp_client, db, bot):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    refused = call(mcp_client, tokens["access_token"], "send_telegram", text="Video đã xong")
    assert refused.get("isError") and "chưa kết nối Telegram" in str(refused)
    link(db, user)
    answer = call(
        mcp_client, tokens["access_token"], "send_telegram", text="Video <b>đã xong</b>", link="https://app.vn/videos/1"
    )
    assert not answer.get("isError"), answer
    sent = bot.telegram_sent("sendMessage")[-1]
    assert sent["chat_id"] == CHAT
    assert (
        sent["text"] == '💬 <b>Muse</b>\nVideo &lt;b&gt;đã xong&lt;/b&gt;\n\n<a href="https://app.vn/videos/1">Mở</a>'
    )
    user.telegram_muted = ["muse"]
    db.commit()
    assert call(mcp_client, tokens["access_token"], "send_telegram", text="x").get("isError")
