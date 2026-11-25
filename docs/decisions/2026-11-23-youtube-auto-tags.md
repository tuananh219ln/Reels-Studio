# 2026-11-23 — YouTube uploads carry the video's hashtags as tags

Asked by the team on 2026-11-22 ([brief](../specs/youtube-auto-tags/brief.md)): the 8 first Shorts arrived in YouTube Studio
with an empty tags field and were tagged by hand.

1. **`snippet.tags` = the video's own hashtags**, without `#` (`hashtags.youtube_tags`): `<` and `>` removed,
   deduped ignoring case in order, at most 500 characters (commas included, a tag with a space counts 2 more); tags
   dropped from the end when over, none left means no `tags` field.
2. **The set is generic** (for Threads videos `reels`, `trendingreels`, `fyp`, ...): it is Facebook's set, used as it
   is. Owner's choice, 2026-11-23.
3. **Tags go out only with a new upload session.** A session already open when this shipped keeps its body.

**Rejected:** adding the topic group's name; a YouTube-specific set per group (as `TIKTOK_HASHTAGS`); per-video topic
tags (would need a column and a way to write them at build time: a separate feature).
