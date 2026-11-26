# 2026-11-26 — Private Telegram messages: each member hears only about their own work

## Context

The team chats on Telegram, and "Có gì mới" ([2026-11-26](2026-11-26-whats-new.md)) posts to the shared group after
each deploy. The owner was explicit that a video to review, an error, a report or a reminder that is not someone's own
must never go to the shared group. They asked for the shared group and a private channel per member, with nothing for
the team to set up beyond linking once, and asked whether Muse can use it.

## Decision

- **One bot, two places.** The same bot (`TELEGRAM_BOT_TOKEN`) posts team-wide news to the group (the CI, unchanged)
  and talks to each member in their own private chat with it (the api and worker). The bot never says anything personal
  in a group; in a group it only answers `/chatid`, for setting the group up.
- **Linked once, from Cài đặt.** "Kết nối Telegram" gives a one-time `t.me/<bot>?start=<code>` link (30 minutes); the
  bot's /start links that chat to the member. No chat id to copy, no username to type. A chat belongs to one member.
- **A webhook, not polling.** Telegram calls `/api/telegram/webhook` (checked with a secret derived from the token),
  so the Duyệt / Bỏ buttons answer at once, even while the worker is busy rendering. It is set when a member links.
  Polling `getUpdates` from the worker was rejected: the worker's loop stops during a render.
- **What is told is read from the database, not hooked into each code path**: `review_requested` events, failed jobs,
  connection errors and the morning's state, each written once as a `telegram_notices` row (key unique per member) and
  sent by the worker between jobs. New ways a job can fail or a video can need review are covered with no change here.
  Only what happened after linking and in the last 24 hours is told.
- **Who is told:** the video's maker (review), whoever queued the job (failures), the Page's / account's owner
  (connections), each member for their own Pages and groups (reminder at 8:00 Vietnam time, only when there is
  something). Each kind can be muted on the settings page.
- **Approving from Telegram is the web's "Duyệt"**, through `review.approve` with the channel `telegram`: the same
  blockers, the warnings acknowledged with "Vẫn duyệt", bound to the MP4 the message showed. It does not schedule or
  post; that stays in the app.
- **Muse can message a member privately** with the MCP tool `send_telegram` (write scope), only to the member whose
  connection it is. Muse's messages are a kind the member can mute.
- Without the token nothing is collected or sent, and the settings page says the bot is off.

## Not done

A weekly views report, a reason typed in Telegram when rejecting, and a note when a post's views jump were offered as
follow-ups.
