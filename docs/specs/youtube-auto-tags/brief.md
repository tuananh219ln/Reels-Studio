# Brief: Auto-tag YouTube uploads (send `snippet.tags` on upload)

Status: not started. Asked for 22/11/2026 after the 8 existing Shorts had to be tagged by hand in YouTube Studio.

## 1. Problem (evidence)

- The tool's YouTube upload sends no tags. All 8 Shorts uploaded 22/11 (videos 286/289/310/311/313/314/312/315) arrived in YouTube Studio with an empty "Thẻ (từ khóa)" field (0/500) and had to be tagged by hand in Studio (done 22/11 ~23:51, 8–12 tags per video, by topic).
- Every future auto-uploaded video will have the same problem until this is fixed: the tool uploads ~6 Threads videos a day, so hand-tagging is not sustainable.
- Tags are a small ranking signal, not a view guarantee: for Shorts, recommendations run mostly on watch behaviour. This fix only makes the metadata complete; it does not promise views.

## 2. What the code does today (verified on `main`, HEAD `fdc172c`)

- `youtube_publish.run` (`api/src/reels_api/youtube_publish.py:59`) builds the upload body once, before the file is sent:
  `body = youtube_upload.metadata(post.caption or video.topic, post.post_text or "")`
  What is saved in `post.upload_url` before sending is the resumable session's URL, not the body, so a retry resumes
  that session. Tags therefore only go out with a session opened after the deploy; a session already open keeps
  its old body (no tags), and that is fine: do not try to patch it.
- `youtube_upload.metadata(title, description)` (`api/src/reels_api/youtube_upload.py:217-230`) returns:
  - `snippet`: `title` (cleaned, max 100 chars) + `description` (max 5000 chars) — **no `tags` field, no `categoryId`**.
  - `status`: `privacyStatus: "private"`, `selfDeclaredMadeForKids: False`, `containsSyntheticMedia: True`.
- The description (`post.post_text`) is the caption plus the video's hashtags (`hashtags.post_text`, `api/src/reels_api/hashtags.py`). The hashtags themselves never reach any tag field.
- `video.hashtags` is a JSONB list on `Video` (`api/src/reels_api/models.py:301`). Entries carry the leading `#` (e.g. `"#threads"`, `"#doccomment"`). There is **no tags column** on any model — nothing to migrate.
- Tests: `api/tests/test_youtube_publish.py`, `api/tests/test_youtube_auto_post.py`. Fake YouTube: `api/scripts/fake_services.py`, `_youtube_upload_start` (around line 1822) already stores the received body in `youtube_uploads[session]["body"]`.
- The 8 hand-tagged videos keep their richer per-video topic tags (e.g. "mẹ chồng", "lương"). Those cannot be derived from anything the tool stores, so they are out of scope here.

## 3. Fix (scope: derive tags from the video's hashtags)

- **F1 — Send `snippet.tags` on upload.** In `youtube_publish.run`, derive the tag list from `video.hashtags` and pass it to `youtube_upload.metadata()` (add a `tags` parameter, default empty = field omitted, so existing callers/tests keep working). `metadata()` must put it in `snippet.tags`.
- **F2 — Tag cleaning (single helper, unit-tested).** From each entry in `video.hashtags`: strip a leading `#` if present; strip `<` and `>` (same as title/description cleaning); drop empty strings; dedupe case-insensitively, keeping first-seen order (reuse `hashtags.merge([], hashtags)` for the dedupe, do not write a second one). Cap the total at 500 characters (YouTube's documented limit for the tags field), counted as `sum(len(tag)) + number of commas between tags`, and a tag containing a space counts 2 more (as if quoted): drop tags from the end until the list fits; if a single tag alone exceeds the limit, drop it. If the list ends up empty, omit `snippet.tags` entirely.
- **F3 — Tests.** Extend `api/tests/test_youtube_publish.py`: (a) an upload whose video has hashtags sends `snippet.tags` with the same words minus `#`, deduped, in order; (b) a video with no hashtags sends no `tags` field; (c) over-long/duplicate/dirty input is cleaned per F2. The fake already records the received body (`youtube_uploads[session]["body"]`): assert on that, no fake change needed.
- **Out of scope (do not build):** no new DB column; no per-video topic-tag generation (no AI/keyword extraction from the title); no backfill of the 8 already-tagged videos (they already have hand tags — do not touch them via `videos.update`); no change to the description, the title, the privacy status, or the auto-post sweep; no change to Facebook/TikTok/Instagram paths.

## 4. What the auto tags will be (so the owner knows the limit)

- Tags = the video's own hashtag set, without `#`. Threads videos get: threads, doccomment, xuhuong, videoviral, reels, trendingreels, fyp. Ăn Lành/Già videos would get their own fixed sets the same way if their pages ever enable YouTube auto-post (currently off, no channel attached).
- The richer topic tags added by hand to the first 8 videos ("mẹ chồng", "lương", "phỏng vấn", ...) will NOT appear on future auto-uploaded videos. If the owner wants those too, that is a separate feature (per-video tag list at build time) — say so in the PR, do not silently expand this one.

## 5. Files to touch

- `api/src/reels_api/youtube_upload.py` — `metadata()` gains `tags`.
- `api/src/reels_api/youtube_publish.py` — build the tag list from `video.hashtags` and pass it.
- `api/src/reels_api/hashtags.py` — put the cleaning helper here if it fits (it owns hashtag words), else next to `metadata()`; one place only.
- `api/tests/test_youtube_publish.py` — tests (F3).
- `docs/architecture.md` — update the `publications` row (YouTube post, `youtube_publish`) and the `jobs` row (`youtube_publish`) if the upload behaviour changes.
- `docs/decisions/2026-11-23-youtube-auto-tags.md` — new decision file: tags come from the video's hashtag set; no per-video topic tags (AGENTS.md: decisions are logged, one file each).

Do not change the Facebook, TikTok, or Instagram publish paths, the sweep, or any schedule.

## 6. Acceptance

- A fake upload for a video with hashtags carries `snippet.tags` with the same words minus `#`, deduped and within 500 characters; a video with no hashtags carries no `tags` field.
- After merge, the owner checks that the next real auto-uploaded Threads video shows its tags in YouTube Studio (an agent never triggers a real upload).
- Per repo `AGENTS.md`: a GitHub issue (Vietnamese form) with `Closes #<n>` in the PR, branch from `main`, `ruff check` + `ruff format --check` clean, tests for the changed behaviour exist and pass, docs updated in the same PR. Never commit to `main` directly.

## 7. Open questions (for the implementer to answer in the PR)

- YouTube's per-tag length limit: the API docs only state the 500-character total; Studio caps a single tag at about 30 characters. Confirm whether the API enforces it, and handle it in F2 if so.
- **Decided 23/11/2026 (owner):** use the video's own hashtag set as is (including the generic `reels`, `trendingreels`, `fyp`). No topic-group name, no YouTube-specific set. Say in the PR that it is generic.
- Should the tag list also include the video's topic-group name (e.g. "tiem doc comment")? The owner did not ask for it; default is no, unless the PR argues otherwise.
