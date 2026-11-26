# Brief: music-claim flag + per-platform status (video 409 YouTube block)

- Date: 2026-11-26
- Author: Muse (for Truong, who sends briefs to the coder himself)
- Status: reviewed 2026-11-26 against main `7b8f45a` and corrected below; the owner chose the four open points
  (see "Review corrections" and [the decision](../../decisions/2026-11-26-youtube-claimed-music.md)); built in the
  same PR as this file.
- Verified against: `origin/main` @ `7b8f45a` (fetched 2026-11-26 21:36) + live tool data
  2026-11-26 21:31. Every file/line claim below was checked on main.
- Related (separate brief, same day): `docs/specs/per-group-qc/brief.md`
  (per-group QC config + title loosening + provenance header).

## 0. Review corrections (2026-11-26)

The first version had these wrong; the sections below are fixed where they matter.

- YouTube auto-upload is switched per **Page** (`Fanpage.youtube_auto` + `youtube_channel_id`,
  `jobs.queue_youtube_auto_posts`), not per group. A video belongs to a group (`knowledge_topic_id`) and has no Page
  until it is scheduled, and any video can be uploaded by hand ("Tải lên YouTube"). **Owner's choice: refuse a claimed
  track for every video.**
- Music reaches a video three ways: "Chọn từ thư viện" (`routes_videos.music_from_library`, which MCP `set_audio`
  calls too), a member's default music (`apply_default_music`), and cloning (copies `music_key`). The refusal goes in
  the shared route and the defaults; clones cannot be checked (a video stores only `music_name`, not the track).
- Slice B mostly exists: `StatusCard` + `web/src/lib/postResults.ts` already show one row per platform tried, with
  errors, "Thử lại" and the Facebook comment state (set-comment failures land in `comment_error`, state `failed`).
  What was missing: YouTube `private` was counted "✓", and no "Bị chặn". **Owner's choice: show "Riêng tư" on its own
  and leave it out of "Đã đăng X/Y".**
- `publications[]` in `get_video` is Facebook only (`status / url / comment`, no `platform / post_stage /
  post_url`); YouTube and Instagram are `manual_posts[]` (status incl. `private`), TikTok `tiktok_posts[]`
  (`status / mode`).
- YouTube code is `api/src/reels_api/youtube_publish.py` (`worker/src/reels_publish` does not exist). "Đọc lựa chọn
  dựng video" is `mcp_server.py:1726` (`:2634` is `add_music_from_link`).
- Group 10 is "Nhóm test", not "Ăn Ngon".
- `video_events` was not shown on the video page; the claim needs its own line there.
- Seeds: a data migration guarded by name (track 3 only if its name starts with "Gentle"; the 409 claim only if 409
  has a YouTube post), since test and development databases reuse the ids. **Owner's choice.**

## 1. Background — what happened

Video **409** (Tiệm Đọc Comment, posted 2026-11-26 21:00 VN) was **blocked
worldwide on YouTube** by a Content ID claim on its background music:

- Asset: `267_the_inspiring_piano_56574246`
- Claimant: **HAAWK Publishing, Audiam (Publishing)**; claim type: melody/lyrics
- This is a **claim, not a strike** — the channel is not penalised.
- The Facebook and Instagram copies of 409 are **live and unaffected**.

The music was **"Gentle – Peaceful Gentle Music", MusicTrack id 3** (mood
piano, topics `[Ăn Lành Sống Khỏe – Sức khỏe]`, created by NamTC
2026-11-08 15:20 VN). Its `license_note` reads verbatim:

> "Pixabay Music – Gentle – Peaceful Gentle Music by BombinSound (Pixabay
> Content License, miễn phí dùng thương mại, không cần ghi nguồn)"

So the track has a free commercial licence, yet a third party still claimed
it on YouTube — a dispute is possible but takes up to 30 days and the video
stays blocked meanwhile. The user handled 409 himself in YouTube Studio on
26/11 (method not recorded in the tool).

Video **443** (day-15, xăng E10) also used track 3; the user ordered a swap
on 26/11 21:29 and it was swapped to track 4 ("Sweet PIANO Whispers") +
re-rendered 21:33. Other tracks in the day-14/15 batches (ids 2, 4, 5, 6, 7)
have no claim. The full library is 15 tracks (ids 1–15).

## 2. Problem — three gaps

1. **No prevention.** Nothing in the tool records that a track was claimed.
   The build job can pick track 3 again tomorrow for another YouTube-bound
   video, and `set_audio` will happily attach it.
2. **No per-platform visibility.** One MP4 is fanned out to Facebook,
   Instagram, YouTube and TikTok, each with its own rules and failure
   surface — but the video page shows no single row saying, per platform,
   posted / draft / failed / blocked. The 409 block was only visible in
   YouTube Studio, not in the tool.
3. **No YouTube-claim detection.** The tool cannot read Content ID claims:
   there is no claim handling anywhere in
   `worker/src/reels_publish/youtube_publish.py` or the API (grep `claim`
   on main returns nothing relevant), and the YouTube Data API exposes no
   Content ID claim state — claims need the Content ID API (CMS account),
   which the tool does not have. Detection must therefore be **manual**,
   and the manual record must live in the tool.

## 3. Scope

Three slices, in priority order:

- **A. Track claim flag (P0, core):** a `claimed_on_youtube` flag on
  `MusicTrack`, enforced at selection time.
- **B. Per-platform status row (P1):** one row per platform on the video
  detail page, built from data the tool already has.
- **C. Manual YouTube-claim record + pre-publish check (P1):** a place to
  record a claim found in YouTube Studio, and a checklist reminder before
  a YouTube private upload is made public.

## 4. Slice A — track claim flag

### 4.1 Data

Migration on `music_tracks` (`api/src/reels_api/models.py`, class
`MusicTrack` — fields today: `id, name, topics (JSONB), mood,
license_note (Text, default ""), storage_key, created_by_id, created_at`):

- `claimed_on_youtube` — BOOLEAN, default FALSE.
- `claimed_at` — TIMESTAMPTZ, nullable.
- `claimed_note` — TEXT, nullable, e.g. `"409 – HAAWK Publishing, Audiam
  (Publishing) – 26/11/2026"`.

### 4.2 Why selection time, not render time

The model docstring says: *"Choosing it for a video copies the file into
the video's folder, so editing or deleting the track never changes a
video."* A flag on the track therefore cannot protect already-built videos
— it must be enforced where a track is **chosen**: `set_audio` and the
track picker the build job reads. Follow the `youtube_meta` pattern
(PR #357: migration `0126_youtube_meta.py` + `youtube_meta.py` +
`api/tests/test_youtube_meta.py`) for how a small config lands in the API,
the web UI and the MCP surface.

### 4.3 Behaviour

- Web library (`/music`, `routes_music.py`): the track row shows a
  **"Đã bị claim trên YouTube"** badge when the flag is set. The edit form
  — the same form that already edits `license_note` (`TrackPatchBody` in
  `routes_music.py`: `name / topics / mood / license_note`) — gets the
  flag + note fields. `track_payload` (and the MCP "Đọc lựa chọn dựng
  video" tool, `mcp_server.py:2634`) must include the flag.
- "Chọn từ thư viện" (`routes_videos.music_from_library`, used by the web
  and by MCP `set_audio`): **refuse** a flagged track for **every** video
  (corrected: there is no per-group YouTube switch). The refusal names the
  track and its note, e.g. *"Bài nhạc “Gentle…” (id 3) đã bị claim trên
  YouTube (Video 409 – HAAWK Publishing…). Hãy chọn bài khác."*
- Default music: a flagged track cannot be saved as a member's default, and
  a default flagged later makes new videos start silent (Cài đặt warns).
- **Seed in the same PR:** set the flag on track 3 with
  `claimed_note = "409 – HAAWK Publishing, Audiam (Publishing) –
  26/11/2026"`. Do not leave this as a later manual step.
- Build-job rotation: the track rotation lives in the **cron job body**,
  not in code — the coder's part is only exposing the flag in the track
  list the job reads. The job body itself is updated separately after
  deploy. The coder must NOT edit any cron/scheduled job.

## 5. Slice B — per-platform status row

On the video detail page (`web/src/app/(app)/videos/[id]/page.tsx`,
near `PublishCard`/`StatusCard`; cards live in
`web/src/components/video/{PublishCard,StatusCard,TikTokCard,
ManualPostCard}.tsx` — coder picks exact placement), add **one row per
platform** — Facebook, Instagram, YouTube, TikTok — each showing, from
**data the tool already has**:

- **Posted** — with link + time. **Draft** (TikTok). **Private** (YouTube
  auto-uploads land private). **Failed** — with the error text.
  **Blocked** — YouTube claim, from the manual record (slice C).
  **Not scheduled.**

Sources (already returned by `get_video` today; no new collection needed):

- `publications[]` — `platform / post_stage / post_url` (model
  `Publication`, `models.py:1055`: one row per post per platform, kept
  after cancel/delete; unique pending per `(video_id, platform)`).
- `manual_posts[]` — YouTube (private) and Instagram published copies.
- `tiktok_posts[]` — `post_stage / url`.
- **Affiliate-comment state** — the Facebook auto comments: posted /
  rejected. Source: the comment publications' state, the same data the
  failure-watch job reads (26/11 it found 7 rejected comments on videos
  361, 364, 386, 392, 393, 395, 396). The row must surface a rejected
  comment, not just the reel.

Reuse the existing retry routes/buttons for failed rows. **No new retry
behaviour** in this brief.

## 6. Slice C — manual YouTube-claim record + pre-publish check

- Add a manual **"YouTube claim" marker** on a video. Storage is the
  coder's choice: either a `video_events` row (`models.py:933`, type
  `approved | rejected | restored | review_requested | publish_skipped`,
  `channel` web | muse_chat | auto | telegram | system, `payload` JSONB
  — a new type such as `youtube_claim_noted` fits) or a column on `Video`.
  Whichever is chosen, the record must be **visible on the video page**
  (timeline or status area).
- Add a **pre-publish checklist item** on the video page: *"Đã kiểm tra
  Content ID trong YouTube Studio"*. The tool's YouTube upload stays
  private, so this is a **checklist, not a gate** — it reminds the person
  who makes the Short public to check claims first.
- **Seed the 409 claim as the first record:** video 409, asset
  `267_the_inspiring_piano_56574246`, claimant HAAWK Publishing, Audiam
  (Publishing), date 26/11/2026, action "user handled in YouTube Studio
  26/11 (method to confirm)".

## 7. Interaction with the review gate (PR #362)

A music swap + re-render returns the video to `pending_review` and
withdraws planned posts (`review.py: after_render`, R2 — verified live on
443 on 26/11), and every posting job re-checks the gate right before
starting (R3; `POSTING_JOBS = ("publish", "tiktok_publish",
"ig_publish", "youtube_publish")`). Nothing in this brief bypasses the
gate: the swap flow stays **set_audio → render → review → approve**.
On a **posted** video, swapping music + re-rendering does NOT change the
posted copies — those are frozen and must be fixed in place per platform
(YT: erase song in Studio, or delete + re-upload a clean render).

## 8. Acceptance criteria (verifiable)

1. Migration applies cleanly; after deploy, track 3 has
   `claimed_on_youtube = true` + the note above (if its name starts with
   "Gentle").
2. `set_audio` with `music_track_id = 3` on any video returns a clear
   refusal naming the track and video 409 (corrected: no per-group
   exception).
3. The web library and the MCP track list show the flag for track 3.
4. Video 409's page shows: **FB posted (link), IG posted (link), YT
   "Bị chặn (claim)" with the claim note under the rows** — all from
   existing data + the manual record. A video only private on YouTube
   shows "Riêng tư, chưa công khai" and is not counted in "Đã đăng X/Y".
5. The 409 claim record is visible on the video page.
6. No change to Facebook/Instagram/TikTok retry behaviour; no
   auto-dispute; no Content ID API integration; no bulk re-render.
7. Tests: mirror `api/tests/test_youtube_meta.py` — cover the flag and
   the `set_audio` refusal.

## 9. Out of scope

- Auto-dispute of claims; Content ID API integration.
- Bulk re-render of videos that used track 3.
- Changing any retry behaviour or any cron/scheduled job body.
- The per-group QC brief (`docs/specs/per-group-qc/brief.md`).
- Track 1 "Wind hill": its `license_note` is **empty** ("Chưa ghi
  nguồn") — a separate follow-up (add the source or drop it from the
  rotation), not part of this brief.
