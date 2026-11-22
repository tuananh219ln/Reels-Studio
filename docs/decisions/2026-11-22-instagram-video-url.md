# 2026-11-22 — Instagram Reels are fetched by Instagram (`video_url`), not uploaded to rupload

Every resumable upload to `rupload.facebook.com` failed with HTTP 400 `ProcessingFailedError` (jobs 1718-1763, retries
included), while a Reel posted by hand with `instagram-cli` the same day worked. The cause was not found (app setup,
file compliance or the request itself are still open, see the [brief](../specs/instagram-upload-fix/brief.md)).

1. **`ig_publish` creates the container with `video_url`** and Instagram fetches the MP4 from our public link, so
   rupload and its conditions are not used. Resumable upload stays only when no public address is set (local dev,
   tests), so nothing else changes.
2. **The link is a sealed token** (Fernet, the storage folder's key): one post id, 6 hours, served without sign-in by
   `GET /api/instagram/media/{token}/video.mp4` only while that post is `pending`. Nothing else is exposed.
3. **Base address:** `INSTAGRAM_VIDEO_BASE_URL`, else the first https origin of `ALLOWED_ORIGINS`; no new env var is
   needed in production if the web domain is there.

**Rejected:** guessing at render changes (audio 128k, edit lists) before the cause is known.
