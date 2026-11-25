# 2026-11-25 — YouTube has its own description and tags, set per topic group

Asked by the team on 2026-11-25 ([brief](../specs/youtube-description/brief.md)): the YouTube description was the
Facebook caption frozen when the YouTube post was made (`Publication.post_text`), so a caption completed later never
reached YouTube (FoodDose 382), and the 5 reference Shorts channels studied that day all use a YouTube description of
their own (Subscribe line, full disclaimer, 10–20 hashtags) and YouTube tags different from their Facebook set.

1. **Built at upload, recorded as sent.** `youtube_publish` builds the description and tags when it opens an upload
   session, from the caption as it is then, and writes the description to the post's `post_text`. A session YouTube
   still holds is resumed with the body it was opened with (as decision 2026-11-23 point 3).
2. **A group setting, not code** (`knowledge_topics.youtube_meta`, migration 0126): YouTube hashtags, keywords,
   Subscribe line (`{channel}` is the receiving channel's name) and disclaimer, edited on Kho kiến thức › Cài đặt nhóm
   › Đăng YouTube and through MCP `get_youtube_meta` / `update_youtube_meta`. Owner's choice (option B of the brief):
   decision 2026-11-13 said a second group's set becomes a group setting, and this is text content, which is app data.
3. **Keywords go to the tags only**, after the YouTube hashtags; a list of keywords in the description is keyword
   stuffing to YouTube. At most 15 hashtags are written in the description (YouTube ignores all of them above 60).
4. **A group with nothing set uploads as before**: the caption and the video's own (Facebook) hashtags, as description
   and tags. FoodDose and Topic Threads start with a set drawn from the reference channels; Topic Threads has no
   disclaimer. Its two Pages (Tiệm Đọc Comment, Tôi Đọc Threads) share the group's set; the Subscribe line names each
   one's own channel.
5. **Facebook, Instagram and TikTok are unchanged.** "Bài đăng" offers the same YouTube text to copy. Videos already
   uploaded keep their description.

**Reverses** the rejection of "a YouTube-specific set per group" in
[2026-11-23-youtube-auto-tags](2026-11-23-youtube-auto-tags.md), on the evidence of the reference channels.

**Rejected:** dicts in code keyed by group name (as `TIKTOK_HASHTAGS`: every wording change a deploy, against decision
2026-11-13); a setting per Page (both Threads Pages share one group and one kind of content; the channel name already
differs); keywords in the description; a stored YouTube caption per video (a second caption to keep in sync).
