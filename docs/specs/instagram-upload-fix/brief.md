# Brief: Fix Instagram Reel upload — rupload 400 `ProcessingFailedError`

Status: diagnosis done 22/11/2026, fix not started. Instagram auto-post (PR #317) has never succeeded once: every `ig_publish` job fails the same way. Facebook and YouTube auto-posts are unaffected — do not touch their code.

## 1. What happened (evidence)

- 22/11/2026, all 9 Instagram jobs failed with the same generic error `Instagram từ chối đăng video này`:
  - Jobs 1718–1722 (auto sweep, 19:29 and 19:54 VN) — videos 311, 314, 313, 286, 289.
  - Jobs 1747 (video 312) + 1748 (video 315) — the 21:00 slots.
  - Retries 1762 (video 315) + 1763 (video 312) — pressed by hand ~21:59, failed again identically.
  - Every job ran ~46 seconds (one waited 53 s in queue first).
- Worker log (Coolify `reels-worker`, read 22/11 ~22:02), the only two error lines:
  - `2026-Nov-22 15:00:33 HTTP 400: {"debug_info":{"retriable":false,"type":"ProcessingFailedError","message":"Request processing failed"}}`
  - `2026-Nov-22 15:01:32 HTTP 400: {"debug_info":{"retriable":false,"type":"ProcessingFailedError","message":"Request processing failed"}}`
  - (15:00 UTC = 22:00 VN; these are the two retries dying.)
- Impact: videos 312 and 315 never reached Instagram. The auto sweep will keep creating failing jobs for every future slot until this is fixed. Workaround for tonight: post 312/315 by hand via `instagram-cli` (as video 310 was posted 22/11 18:22) and record them as manual posts. Do NOT press retry again — `retriable: false` and two retries already failed identically.

## 2. Where it fails (verified in code on `main`, HEAD `cbe4a92`)

- The error body is `{"debug_info": ...}`. That is **not** a Graph API error shape (Graph errors are `{"error": {"message", "code", "error_subcode", ...}}`). It is the shape `rupload.facebook.com` returns. So the failing call is the file upload, `instagram.upload()` in `api/src/reels_api/instagram.py:154-172` — the POST of the MP4 bytes to `{INSTAGRAM_UPLOAD_URL}/{container_id}`.
- The container creation (`POST /{ig-user-id}/media`, `media_type=REELS`, `upload_type=resumable`) **succeeded**: a failed creation would end the job in ~1–2 s with a Graph-shaped error, not after 46 s with a rupload-shaped error. The 46 s is the upload transfer, then the rejection.
- Why the UI shows only the generic sentence: `_http_error` (`api/src/reels_api/facebook.py`) parses `json.loads(body)["error"]` for a code; on a `debug_info` body that raises `KeyError`, so `code` is `None` and the message falls through to `REFUSED` (`Facebook từ chối đăng video này`), which `instagram._error` rewords as `Instagram từ chối đăng video này`. The raw body IS saved in `jobs.error_detail` (`jobs.py:294`, `worker.py:255`), but no surface shows it: `GET /api/jobs` (`routes_videos.py`, `list_jobs`) returns only `error`, and the video payload's `failed_job` (`videos.py:1234`, `_job_payload` includes `error_detail`) was `null` here because a newer done job (the Facebook check) masks the failed one (`_last_failed`, `videos.py:632`).

## 3. Ruled out (with evidence — do not re-investigate these)

- **Permissions.** The token carries `instagram_basic` + `instagram_content_publish` (checked by the user 22/11 evening). The container creation, which needs them, succeeded.
- **Token validity.** Facebook posting with the same token worked all day (all 7 slots posted; check jobs 1757/1758 done).
- **Instagram account assignment.** Verified in Business Settings 22/11 21:58: both `@tiemdoccomment` and `@toidocthreads` are assigned to System User `ReelsStudioPublisher` with full access (8 assets: 5 Pages + 1 app + 2 IG accounts).
- **moov atom position.** The final render uses `-movflags +faststart` (`worker/src/reels_render/graph.py:602-603`), so moov is at the front as Meta requires.
- **Chunking is required.** Meta's docs do NOT require splitting the file: their example sends the whole file in one POST with `--data-binary`. "Resumable" only means resuming after an interruption. Do not "fix" this by chunking unless the curl test (§5) proves chunking is the difference.
- **Duration / file size limits.** Video 312 is 113.4 s (spec: 3 s–15 min); the render is libx264 preset medium CRF 20, 1080×1920 30 fps — far under the 300 MB spec limit. Exact byte size was not measured; the fix must log it (§6, F3).
- **The videos themselves.** Video 310 (113.2 s, same render pipeline) was posted to `@tiemdoccomment` via `instagram-cli` 22/11 18:22 and is live. The file is postable to Instagram — the tool's upload path is what fails.

## 4. Meta's documented spec (read 22/11 from developers.facebook.com)

- Content Publishing page (updated 20/10/2026), Resumable Uploads page (updated 15/3/2026), IG User Media reference.
- Upload: `POST https://rupload.facebook.com/ig-api-upload/<API_VERSION>/<IG_MEDIA_CONTAINER_ID>`, headers `Authorization: OAuth <ACCESS_TOKEN>`, `offset: 0`, `file_size: <bytes>`, body = the file (`--data-binary`). Success response: `{"success":true,"message":"Upload successful."}`.
- Container creation returns `{"id": "<IG_MEDIA_CONTAINER_ID>", "uri": "https://rupload.facebook.com/ig-api-upload/<API_VERSION>/<IG_MEDIA_CONTAINER_ID>"}`. **The code ignores `uri` and builds the URL itself** from `INSTAGRAM_UPLOAD_URL` (default `https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}`, `GRAPH_VERSION = "v26.0"` in `config.py:160`); the docs' example uses `v27.0`.
- Reel specs: MOV/MP4, **no edit lists**, moov atom at front; H.264/HEVC progressive, closed GOP, 4:2:0; AAC ≤48 kHz, 1–2 channels; **audio bitrate 128 kbps**; video ≤25 Mbps VBR; 3 s–15 min; ≤300 MB. Note: the render uses AAC **160k** (`graph.py`, `-b:a 160k`) — above the 128 kbps spec line.
- "Only for apps that have implemented Facebook Login for Business." (resumable upload scoping, Resumable Uploads page.)

## 5. Root-cause hypotheses (ranked — test before changing code)

- **H1 — The app has not implemented Facebook Login for Business.** Meta scopes resumable upload to such apps. The `Reels Report Tool` app may lack this product. Check in developers.facebook.com → the app → products/use cases. If missing, adding it is a console change, not code. This is the leading hypothesis because everything else in the flow (Graph calls, permissions, assignment, file) is verified working.
- **H2 — Upload URL built instead of using the returned `uri`.** The code constructs `.../ig-api-upload/v26.0/<id>`; the container creation returns the exact `uri` to use. Low probability on its own (Graph `v26.0` calls work), but using `uri` is what the API returns it for, and it removes the version question entirely.
- **H3 — MP4 container compliance: edit lists, or audio 160k vs the 128 kbps spec.** FFmpeg's MP4 muxer can write an edit list (`elst`); the render's audio is 160k against a 128 kbps spec line. Weakened by the `instagram-cli` success with the same file — unless the CLI used `video_url` (Meta fetches and reprocesses) instead of resumable upload. Verify with `ffprobe` on the actual MP4 (check `elst` box, audio bitrate) before changing the render.
- **H4 — The Python upload request itself.** `instagram.upload()` sends the file as `data=file` through `urllib` with hand-set `Content-Length`. The documented curl example is the reference. A difference in how the bytes/headers actually go out is possible but unproven.

## 6. Decisive test first (do this before writing fix code)

Reproduce the upload with `curl` from the VPS, using the **same** Page token the worker uses, the **same** MP4 file from storage, and the **same** URL/headers as `instagram.upload()`:

```
curl -X POST "https://rupload.facebook.com/ig-api-upload/v26.0/<CONTAINER_ID>" \
  -H "Authorization: OAuth <PAGE_TOKEN>" -H "offset: 0" -H "file_size: <BYTES>" \
  --data-binary "@/path/to/video.mp4"
```

(create a fresh container first with `POST /{ig-user-id}/media`, `media_type=REELS`, `upload_type=resumable`, same caption; use its `id` and its returned `uri` in a second run.)

- If `curl` succeeds → the bug is in the Python upload code (H4): fix the request construction in `instagram.upload()`.
- If `curl` fails with the same `ProcessingFailedError` → the bug is not the code's request: it is the file (H3), the URL/version (H2), or the app setup (H1). Then check H1 in the developer console, `ffprobe` the file, and retry with the returned `uri`.

## 7. Fix (code changes)

- **F1 — Use the `uri` from container creation.** `instagram.create_container()` must return the `uri` alongside the `id`; `instagram.upload()` must POST to that `uri` instead of building the URL from `config.instagram_upload_url()` + `GRAPH_VERSION`. Keep the env override only for tests.
- **F2 — Parse rupload errors.** `_http_error` (`facebook.py`) must recognise the `debug_info` shape (`type`, `message`, `retriable`) and surface it, e.g. `Instagram không nhận file video (ProcessingFailedError: Request processing failed)` instead of the generic refusal. `instagram._error` must pass that message through. And `GET /api/jobs` (`routes_videos.py`, `list_jobs`) must include `error_detail` in each row, and the web job log must show it, so the next failure is diagnosable from the UI without reading worker logs.
- **F3 — Log the upload.** At info level in `ig_publish.run` / `instagram.upload()`: file size in bytes, container id, upload URL host + version, and on failure the raw error body. A failed Instagram upload must never again be diagnosable only from a screenshot of Coolify logs.
- **F4 — Tests.** Extend the fake (`api/scripts/fake_services.py`, `_instagram_upload`): return a `debug_info` error for a chosen case, return the `uri` from container creation, and accept a large file. Add tests in `api/tests/test_instagram_publish.py`: (a) upload uses the returned `uri`; (b) a `debug_info` failure surfaces Meta's real message in the job error; (c) the job log row carries `error_detail`. The existing test MP4 is 1,600 bytes (`b"fake mp4 bytes " * 100`) — it never exercised a real-size upload; add a multi-MB file case.
- **F5 (only if H1 is confirmed)** — Add Facebook Login for Business to the `Reels Report Tool` app in the developer console; no code change.
- **F6 (only if H3 is confirmed)** — Fix render compliance (`worker/src/reels_render/graph.py`): audio to 128k, and strip edit lists if `ffprobe` shows an `elst` box. Do not change the render on speculation — `ffprobe` first.

## 8. Files to touch

- `api/src/reels_api/instagram.py` — `create_container` (return `uri`), `upload` (POST to `uri`), `_error` (pass through rupload messages).
- `api/src/reels_api/facebook.py` — `_http_error` (parse `debug_info`).
- `api/src/reels_api/routes_videos.py` — `list_jobs` (include `error_detail`) + the web job-log UI that renders it.
- `api/src/reels_api/ig_publish.py` — logging only (F3).
- `api/scripts/fake_services.py`, `api/tests/test_instagram_publish.py` — fake + tests (F4).
- `worker/src/reels_render/graph.py` — only if F6 is confirmed needed.
- `docs/architecture.md` — update the Instagram paragraph (§6.06) if the upload behaviour changes.

Do not change the Facebook, TikTok, or YouTube publish paths. Do not change the sweep, the dedupe rule (a failed Instagram publication still blocks a new one — retry is the path), or any schedule.

## 9. Acceptance

- Pressing "Thử lại" on jobs 1747 (video 312) and 1748 (video 315) publishes both Reels, with permalinks on `@tiemdoccomment` and `@toidocthreads`.
- The next auto-sweep slot posts its video to Instagram with no manual help.
- A future Instagram failure shows Meta's real error text in the job log (not the generic sentence).
- Per repo `AGENTS.md`: branch from `main`, `ruff check` + `ruff format --check` clean, `npm run` checks if web touched, tests for the changed behaviour exist and pass, docs updated in the same PR. Never commit to `main` directly.

## 10. Open questions (for the implementer to answer in the PR)

- Does the `Reels Report Tool` app have Facebook Login for Business implemented? (H1 — check the console first.)
- What does `ffprobe` say about video 312's MP4 — `elst` box present? Audio bitrate?
- What is the exact byte size of a 113 s render, and does the curl test (§6) succeed with it?
