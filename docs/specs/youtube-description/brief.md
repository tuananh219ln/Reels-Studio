# Brief: A YouTube description and hashtag set of its own (apart from the Facebook caption)

Status: built (option B), same PR. Written 25/11/2026, approved by Truong ("làm cả hai", evening of 25/11). Revised the
same day after a review against `main` (HEAD `d7f5799`); the owner chose option B, with an MCP tool and seeded values.
Decision: [2026-11-25-youtube-description](../../decisions/2026-11-25-youtube-description.md).

## 0. What was found while building

- **Tiệm Đọc Comment and Tôi Đọc Threads share one group, "Topic Threads"** (id 9). The set is per group, so both
  Pages share it; the Subscribe line names each Page's own channel.
- **Case (2), "90% đám cưới" (video 397):** its caption is complete ("…tội đơn vị tổ chức quá?") and its YouTube post
  (639) was made by the auto round at 21:03 on 25/11, after the caption's last edit on 24/11. The snapshot cannot cut it,
  and the app does not cut a description this short. Most likely YouTube's own fold ("...more") of the description in
  the Shorts player, not a bug: open it in Studio to check. No failing test could be written for it; the regression
  test is for case (1).

## 1. Problem (verified on `main`, 25/11)

- The YouTube description is `Publication.post_text`, a snapshot frozen when the YouTube post is made:
  `post_text = hashtags.post_text(video.caption, video.hashtags)`, written in two places:
  - `jobs.queue_youtube_auto_posts` (`api/src/reels_api/jobs.py:1389`), the auto round;
  - `routes_youtube.py:191`, the "Tải lên YouTube" button.

  `youtube_publish.run` (`api/src/reels_api/youtube_publish.py:75`) sends that snapshot. A caption edited after the
  post was made never reaches YouTube, and "Thử lại" sends the same text again.
- Tags are computed at upload time (`hashtags.youtube_tags(video.hashtags or [])`, `youtube_publish.py:74`), so they
  follow the current hashtags. Only the description is stale.
- Cases met:
  - (1) FoodDose 382: the YouTube description is shorter than the caption (missing the third pair, the CTA and the
    disclaimer). Consistent with the snapshot: the caption was completed after the post was made.
  - (2) Threads, Short "90% đám cưới": the description stops mid-sentence. **Not yet proven to be the same cause.**
    The snapshot explains it only if the caption was edited after the YouTube post was made. Step 0 below checks it.
- The Facebook caption and the YouTube description are forced to be the same text. The reference channels (5 English
  health Shorts channels, research 25/11, page "FoodDose YouTube Setup") use on YouTube: hook, list of foods, a "No
  single food can cure…" line, a Subscribe CTA, a full disclaimer, 10–20 hashtags, and keywords. Facebook keeps its
  5 fixed hashtags and "Like and follow". One shared caption cannot serve both.
- The "Bảng bài đăng" copy button for YouTube also shows the Facebook text: `posts_board.py:616` returns
  `captions.youtube = post_text`.

## 2. Logged decisions this conflicts with (Truong decides before coding)

1. `docs/decisions/2026-11-23-youtube-auto-tags.md` rejected "a YouTube-specific set per group (as
   `TIKTOK_HASHTAGS`)". This brief proposes reversing it, on the evidence of the 5 reference channels (all five use a
   YouTube hashtag set and keywords different from their own Facebook set).
2. `docs/decisions/2026-11-13-tiktok-caption.md` says the TikTok set lives in code only while one group uses it: "if a
   second group starts on TikTok, the set becomes a group setting". The YouTube text per group (hashtags, keywords,
   CTA, disclaimer) is content, and AGENTS.md says "prompt text is app data, the output format is code". Two options:
   - **A. Dicts in code** (`YOUTUBE_HASHTAGS`, ... keyed by group name, as `TIKTOK_HASHTAGS`). Small PR, no migration;
     each wording change is a code PR and a deploy. The new decision file must say it knowingly departs from the
     13/11 rule.
   - **B. A YouTube section in the group's settings** (new columns on `knowledge_topics`, a migration, a form on the
     group page). Follows the 13/11 rule; owners edit the text themselves. Larger: api + web, and the brief's "no web
     UI in v1" no longer holds.

## 3. Design (written for option A; with B the values come from the group row instead of the dicts)

Precedent: `TIKTOK_HASHTAGS` and `tiktok_caption(caption, topic_name)` in `api/src/reels_api/hashtags.py`. The TikTok
caption is **derived when read, never stored** (no `Video.tiktok_caption` column; `GET /api/videos/{id}` returns a
computed `tiktok_caption`). The YouTube description follows the same rule.

0. **Confirm case (2) first.** For the "90% đám cưới" video, compare its YouTube post's `post_text` with the
   video's current `caption`. If they differ, the cause is the snapshot. If they are the same, the cut comes from
   somewhere else (the caption itself, or YouTube's own "...more" fold) and needs its own failing test before any fix,
   per AGENTS.md.
1. **Per-group YouTube values**, keyed by the group's name (`KnowledgeTopic.name`, as `TIKTOK_HASHTAGS`):
   - `hashtags`: 10–20 tags. FoodDose includes `#FoodDose`. Tiệm Đọc Comment and Tôi Đọc Threads each get their own set
     (the group owner supplies the values; they are not in this brief yet).
   - `keywords`: comma-separated keywords ("food is medicine, healthy foods, ...").
   - `cta`: the Subscribe line, with the channel name filled in (see 3).
   - `disclaimer`: the full disclaimer, **or none** (the Threads groups need no health disclaimer).

   A group with no entry keeps today's behaviour: caption + `video.hashtags`.
2. **Keywords go into `snippet.tags`, not the description.** A list of keywords in the description risks YouTube's
   spam policy (keyword stuffing). Tags = `youtube_tags(group keywords + group hashtags)`, which already handles the
   500-character limit. Without a group entry, tags stay `youtube_tags(video.hashtags)`.
3. **The channel name for the CTA** is `Channel.name` of `post.channel_id` (the YouTube channel the post goes to),
   not the group name: two Pages could share a group but upload to different channels.
4. **`youtube_description(caption, topic_name, channel_name)`** in `hashtags.py`: the caption without its trailing
   hashtags (`strip_trailing_tags`), then the CTA, then the disclaimer, then the group's YouTube hashtags, each block
   separated by a blank line (as `post_text`).
   - **Length:** the whole text must fit 5000 characters (`youtube_upload.MAX_DESCRIPTION`). `metadata()` cuts from
     the end, which would drop the hashtags first, so `youtube_description` shortens the caption part instead, keeping
     the tail blocks whole.
   - Hashtags: at most 15 in the description. YouTube ignores every hashtag in a description that has more than 60,
     and shows the first 3 above the title.
5. **Build at upload, record what was sent.** In `youtube_publish.run`, when a new upload session is opened: the
   description = `youtube_description(video.caption, group name, channel name)`, and that text is written to
   `post.post_text` in the same commit that saves `upload_url`, so the post records exactly what YouTube received.
   - The two creation points (`jobs.py`, `routes_youtube.py`) may keep writing a `post_text`; it is replaced at
     upload. Update their comment "so Thử lại sends the same": it no longer holds.
   - "Thử lại" with a session YouTube still holds resumes it with its old body (decision 23/11 point 3). A retry
     whose session is gone builds a new description from the current caption.
   - Unchanged: the title (`post.caption or video.topic`), `privacyStatus` private, the session URL saved before the
     file is sent.
6. **`posts_board.py`**: `captions.youtube` returns the same `youtube_description` (channel name from the Page's
   `youtube_channel_id` if there is one, else no CTA name), so the copy button matches the upload. API change only,
   no new screen.
7. **Unchanged:** the Facebook caption and its 5 hashtags, Instagram, the daily build jobs (FoodDose 14:00, Threads
   17:30), MCP (no YouTube tool is added).
8. **No backfill.** Videos already uploaded (FoodDose 376/382, the Threads videos) keep their description; edit by
   hand in Studio if wanted.

## 4. Acceptance tests

- Unit (`api/tests/test_hashtags.py`): `youtube_description` for a group with an entry (CTA with the channel name,
  disclaimer, hashtags, trailing Facebook tags removed), a group with no disclaimer, a group with no entry (today's
  text), and a caption long enough to need shortening (the tail blocks stay whole, total ≤ 5000).
- `api/tests/test_youtube_publish.py` (fake YouTube records the body in `youtube_uploads[session]["body"]`):
  - a caption edited **after** the YouTube post is made reaches the description (the regression test for case 1:
    write it first and watch it fail on today's code);
  - tags = group keywords + group hashtags, not the Facebook set;
  - `post.post_text` equals the description sent;
  - a resumed session sends no new body.
- `api/tests/test_youtube_auto_post.py`: the auto round's upload gets the same description.
- The Facebook caption sent for the same video is unchanged.

## 5. Docs in the same PR

- A new decision file in `docs/decisions/` reversing the 23/11 rejection (and, for option A, the 13/11 rule).
- `docs/architecture.md` / `docs/content.md` where they describe what is sent to YouTube.

## 6. Open values (owners supply before or during the PR)

- FoodDose: hashtag set, keywords, CTA wording, disclaimer text.
- Tiệm Đọc Comment, Tôi Đọc Threads: hashtag set, keywords, CTA wording (disclaimer: none, unless the owner says
  otherwise).

## 7. Related files

- `api/src/reels_api/hashtags.py` (`TIKTOK_HASHTAGS`, `tiktok_caption`, `post_text`, `youtube_tags`,
  `strip_trailing_tags`)
- `api/src/reels_api/youtube_publish.py` (`run`)
- `api/src/reels_api/youtube_upload.py` (`metadata`, `MAX_DESCRIPTION` 5000, `MAX_TITLE` 100)
- `api/src/reels_api/jobs.py` (`queue_youtube_auto_posts`), `api/src/reels_api/routes_youtube.py` (upload button)
- `api/src/reels_api/posts_board.py` (`captions.youtube`)
- `api/src/reels_api/models.py` (`KnowledgeTopic.name`, `Channel.name`, `Publication.channel_id`)
- `docs/decisions/2026-11-23-youtube-auto-tags.md`, `docs/decisions/2026-11-22-youtube-auto-post.md`,
  `docs/decisions/2026-11-13-tiktok-caption.md`

## 8. Out of scope

- Channel setup (About, banner, email, playlists, pinned video, Community posts): done in YouTube Studio, not code.
- The 2 FoodDose videos that went public while the tool uploaded them private (21:46): ask who made them public;
  not handled here.
