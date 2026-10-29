# Code Research: web-video-render

Created: 2026-10-29. Branch `userspec/web-video-render`. Scope from the interview so far: topic →
compact Claude script (one editable system prompt) → scene editor (text/seconds/keywords,
add/delete/reorder, pick 1 of 5 titles, frame preview) → images per scene (upload / auto Pixabay /
pick from Pixabay results) → optional mp3 upload → server render via `reels_render.render_video` →
result page (player, MP4 download, copy caption+hashtags, duplicate).

State of the repo: only the render core (`worker/`) and the web/api auth skeleton exist. There is
no Video/Scene/Asset/RenderJob model, no queue, no worker service, no storage dir, no Anthropic SDK,
no Redis, no upload endpoint anywhere in code (grep for `anthropic|redis|STORAGE_DIR|UploadFile|
multipart` over `api/ worker/ web/src .github` finds nothing outside `api/.venv`).

---

## 1. Entry Points

### Render core (`worker/src/reels_render/`)

- `render.py:27` — the callable the server will use:
  `render_video(script: Script, output: Path, music: Path | None = None, music_volume: float = 0.25,
  on_warning: Callable[[str], None] | None = None) -> Path`.
  - `render.py:41` `ffmpeg.find_tools()` first (raises `ToolNotFoundError` without ffmpeg/ffprobe).
  - `render.py:42-49` validates output path, volume (0..1, not bool), music file exists.
  - `render.py:51-57` lays out every text box (`TextFitError` → `InputError` with scene label) and
    builds the timeline **before** any network or FFmpeg work.
  - `render.py:59` all intermediates live in `tempfile.TemporaryDirectory(prefix="reels_render_")`
    (system temp, deleted afterwards): stock downloads, normalized JPEGs, text PNGs.
  - `render.py:61-63` `find_stock_images(...)`; leftover scenes → `MissingImagesError`.
  - `render.py:77` output is written to `.{stem}.*.tmp` **next to the target** (`dir=output.parent`),
    then `_publish` (`render.py:98`) `os.replace`s it; if the target is locked it saves
    `name.new.mp4` / `name.new-N.mp4` and raises `OutputNotReplacedError(kept_path=...)`.
  - Synchronous, blocking, CPU-heavy (libx264 `-preset medium -crf 20`, `graph.py:102`); must not
    run in the API request thread.
- `script.py:219` `parse_script(data: object, base_dir: Path) -> Script` — builds a `Script` from a
  plain dict (no file needed). `load_script(path)` (`script.py:202`) is the file wrapper. Only
  `load_script` is re-exported in `__init__.py`; `parse_script` is importable from
  `reels_render.script`.
- `cli.py:34` `main(argv)` — CLI only; the interactive "drag an image in" flow (`cli.py:77-135`) is
  CLI-only and irrelevant to the server.
- `__init__.py` exports: `render_video`, `DEFAULT_MUSIC_VOLUME`, `load_script`, `Scene`, `Script`,
  `find_stock_images`, `StockResult`, and all error classes.

### API (`api/src/reels_api/`)

- `main.py:14` `create_app() -> FastAPI` (factory; uvicorn `--factory`). Docs/OpenAPI disabled.
  Middleware `check_origin` (`main.py:18-27`): POST/PUT/PATCH/DELETE need `Origin` in
  `ALLOWED_ORIGINS`, else 403 `origin_not_allowed`. Exception handlers for `ApiError`,
  `RequestValidationError` (422 `invalid_request`, never echoes input), `OperationalError` (503
  `database_unavailable`). Routers: `routes_auth.router` (prefix `/api`), `routes_users.router`
  (prefix `/api/users`). A new `routes_videos.py` would be included the same way.
- `routes_auth.py:53-104`: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/me`,
  `PATCH /api/me`, `POST /api/me/password`.
- `routes_users.py:66` `GET /api/users?q=` etc. — the reference pattern for a CRUD router: pydantic
  body models, `Depends(current_member)`, `Depends(get_db)`, `ApiError(status, code, vi_message)`,
  payload dict builders (`_user_payload`, `routes_users.py:33`).

### Web (`web/src/`)

- `app/(app)/videos/page.tsx:1-5` — placeholder: `<EmptyPage title="Video" description="Chưa có
  video nào" />`. Login lands here (`e2e/helpers.ts:25` expects `/videos`).
- `app/(app)/jobs/page.tsx`, `app/(app)/music/page.tsx`, `app/(app)/knowledge/page.tsx` —
  "Sắp có" placeholders (E2E test "coming-soon pages from the menu", `e2e/app.spec.ts:82`, asserts
  them; changing them breaks that test).
- `app/(app)/layout.tsx` wraps pages in `AppShell`; `components/AppShell.tsx:25-29` NAV: `/videos`
  "Video", `/knowledge`, `/music`, `/users`, `/jobs`.
- `proxy.ts:7-16` — cookie-only redirect to `/login`; matcher already covers `/videos/:path*` and
  `/jobs/:path*`, so new nested pages (`/videos/new`, `/videos/[id]`) are protected without changes.

## 2. Data Layer

- `api/src/reels_api/models.py` — SQLAlchemy 2 declarative, `Base` with naming convention
  (`models.py:6-16`). Tables: `users` (`models.py:19-32`), `sessions` (`models.py:35-44`). Typed
  `Mapped[...]`/`mapped_column`, `DateTime(timezone=True)` with `server_default=func.now()`.
- `api/migrations/versions/0001_users_and_sessions.py` — the only migration (revision `"0001"`,
  hand-written `op.create_table` with explicit constraint names). New tables need `0002_...` with
  `down_revision = "0001"`.
- `api/migrations/env.py:14` uses `sqlalchemy.url` from config (tests) or `database_url()`;
  `target_metadata=Base.metadata`.
- Migrations run on every api container start (`api/Dockerfile` CMD `alembic upgrade head && exec
  uvicorn ...`); deployment.md:217-218 requires migrations compatible with the previous api version
  until the web deploy finishes.
- Planned data model (architecture.md:123-133): Video (topic, title options, chosen title, caption,
  hashtags, affiliate suggestions + pinned comment, self-review notes, content language, TTS on/off,
  music track), Scene (order, seconds, text with `*red*`, image prompt/keywords, assigned Asset),
  Asset (uploaded photo / stock image / music; source and license info), RenderJob (status, timings,
  output file, error, re-run of previous job), KnowledgeDoc, FoodItem. architecture.md:86-89: "The
  title scene has its own image and length ... the data model has no field for these yet; the spec
  that connects stored videos to the renderer must add one." Interview additions not in the model:
  suggested music name, one uploaded mp3 per video, the editable system prompt (app data,
  patterns.md:13-14).

### Script JSON contract the renderer accepts (`script.py:219-307`)

```
{ "title":  {"text": str, "seconds": number>=1, "image"?: str, "keywords"?: [str]},
  "scenes": [ {...same...}, ... ]  // >= 1 scene }
```

- `text`: `*...*` red markup, `\n` manual line break; parsed by `markup.parse_scene_text`
  (`markup.py:20`): NFC + uppercase, rejects empty text, blank lines, unpaired `*`, empty `**`.
- `seconds`: int/float, not bool, finite, `>= 1` (`script.py:251-257`). No upper bound beyond 1e9.
- `image`: string path resolved as `base_dir / image` (`script.py:273-277`) — an absolute path also
  works (pathlib join with an absolute right side). Missing file → `missing_image` set and stock
  search used (warning).
- `keywords`: list of non-empty strings ≤ 100 chars (`script.py:290-307`). A content scene without
  keywords is searched by its first text line (`script.py:269-270`); the title scene is searched only
  with explicit keywords.
- Text fit limits (`textbox.py:36-37`): title 96→64 px, ≤ 5 lines; scenes 84→60 px, ≤ 3 lines,
  box ≤ 960 px wide. Violations surface as `InputError("Cảnh N: chữ quá dài ...")` before FFmpeg.

## 3. Similar Features / Reusable Pieces

- **Frame preview (cheap, no FFmpeg):** all pieces exist in Pillow:
  - `textbox.layout_text(lines, style) -> TextLayout` (`textbox.py:102`), raises `TextFitError`.
  - `textbox.render_box(layout) -> PIL.Image` RGBA yellow box (`textbox.py:136`).
  - `textbox.title_box_position(w, h)` (centered) / `scene_box_position(w, h)` (bottom at y=1440)
    (`textbox.py:151-156`); `FRAME_WIDTH=1080`, `FRAME_HEIGHT=1920`.
  - `images.normalize_image(src, dst, label)` (`images.py:166`) bakes EXIF rotation.
  - Missing: a Pillow cover-crop to 1080×1920 (the crop is done only inside the FFmpeg graph,
    `graph.py:48-49`, with a 1.00→1.12 zoom so frame 0 = zoom 1.00 = plain center cover-crop).
    A preview = cover-crop + `paste(box, position, box)`. Alternative: the API returns only the text
    box PNG and the browser overlays it on the image with CSS (positions are deterministic).
  - Note the render's first frame is zoom 1.00 with no fade-in on the title; preview of frame 0 is
    exact; later frames of a scene are zoomed up to 12%.
- **Pixabay candidate list for a picker UI:** `stock.Pixabay(key).search(keyword, label, warn) ->
  list[str]` (`stock.py:145`) already returns up to `CANDIDATES = 10` (`stock.py:25`) https
  `largeImageURL`s in relevance order, with the 24 h disk cache (`SearchCache`, `stock.py:103`,
  keyed `sha256("pixabay|vi|{keyword}")`). Gaps for a preview grid:
  - only `largeImageURL` is kept; no `previewURL`/`webformatURL` (thumbnails), id, or size. The
    cache stores only the URL list (`stock.py:131`), so adding fields changes the cache format.
  - per_page fixed at 10, `lang=vi`, `image_type=photo`, `safesearch=true` (`stock.py:150-159`).
  - `Pixabay.download(url, target) -> bool` (`stock.py:199`) fetches ≤ 15 MB, validates with
    Pillow; usable to persist the member's chosen photo as an Asset.
  - HTTP 400 "API key" → `StockSearchError`; other 4xx → warning + `[]`; 429/5xx/network → one
    retry after 5 s (`RETRY_DELAY`, blocking `time.sleep`) then `StockSearchError`
    (`stock.py:178-197`). A synchronous API handler calling this can block up to ~2×15 s + 5 s.
  - architecture.md:107: Pixabay terms = download images (no hotlinking) and cache searches 24 h;
    "A future web UI that lists Pixabay results must show 'Ảnh từ Pixabay'." Showing thumbnails in
    the browser directly from Pixabay CDN vs proxying/downloading them is an open decision.
- **Auto stock fill during render:** `find_stock_images(script, work_dir, on_warning, client, rng)`
  (`stock.py:222`) fills only scenes with `image is None` and keywords; random among the first 3
  unused results (`PICK_FROM=3`), so re-renders vary; stock photos live only in the render temp dir
  and are not persisted or reported back (StockResult has `.script` with temp paths, but
  `render_video` does not return it).
- **Atomic file write pattern:** `script.write_scene_image` (`script.py:310`), `SearchCache.put`
  (`stock.py:125`), `render._publish` — mkstemp in the same dir + `os.replace`.
- **API CRUD pattern:** `routes_users.py` (list/search with `select`, refusals via `ApiError`,
  row-locking with `with_for_update` for concurrency, tested in `api/tests/test_concurrency.py`).
- **Web page pattern:** `app/(app)/users/page.tsx` — `"use client"`, antd `App.useApp()` for
  `message`/`modal`, `api<T>()` + `ApiError` catch → `message.error(err.message)`, antd
  `Table`/`Modal`/`Form`.

## 4. Integration Points

- **api ↔ worker package:** the api must not import `reels_render` as things stand:
  - Coolify builds the api with base directory `/api` (deployment.md:198) and `api/Dockerfile`
    copies only `pyproject.toml`, `src`, `alembic.ini`, `migrations`; `../worker` is outside the
    build context.
  - `python:3.12-slim` has no FFmpeg.
  - architecture.md:17-18 / patterns.md:5-7: renders and Claude generation run in the worker via
    the queue, never in the API process.
  - Frame preview and Pixabay search are light (Pillow / HTTP) but live in `reels_render`. Using
    them from the api requires either packaging `worker` into the api image (build context = repo
    root) or duplicating/moving code, or having the worker serve them. Open decision.
- **Shared config:** `api/src/reels_api/config.py:48` and `worker/src/reels_render/env.py:241` are
  duplicate `read_env` implementations (env var wins, else repo-root `.env` via
  `Path(__file__).resolve().parents[3]`). Inside an installed (non-editable) container package
  `parents[3]` points into site-packages, so containers must use real env vars.
- **Web → API:** `web/next.config.ts:41-43` rewrite `/api/:path*` → `${API_URL}/api/:path*`
  (baked at build). `web/src/lib/api.ts:51` `api<T>(path, method: "GET"|"POST"|"PATCH", body?)`
  always JSON-encodes; no `PUT`/`DELETE` and no `FormData` support yet — uploads need a separate
  helper (do not set `Content-Type` for FormData). Error mapping: `not_authenticated` →
  `/login`, `password_change_required` → `/change-password`, non-JSON → `connection`.
- **Auth:** `sessions.current_member` (`sessions.py:150`) for every app endpoint; it commits a
  session renewal before the endpoint body (`sessions.py:136-146`). Media GETs (`<img src>`,
  `<video src>`, download links) carry the cookie automatically (same origin, SameSite=Lax) and are
  not CSRF-checked (GET). Uploads (multipart POST) pass the Origin check because the browser sends
  `Origin`; OpenNext's fetch proxy forwards request headers.
- **Claude:** no code yet. Planned env `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default
  `claude-sonnet-5-5`, architecture.md:104, deployment.md:235-236). content.md:34-56 defines the
  6-part output contract. Placement per architecture: worker job.
- **Queue:** Redis planned (`REDIS_URL`, deployment.md:245), not in `docker-compose.yml` (postgres
  only) nor in code. `RENDER_CONCURRENCY` default 1, `STORAGE_DIR` planned (deployment.md:246-247).

## 5. Existing Tests

- **worker** (`worker/tests/`, pytest, run from `worker/`): `conftest.py:25-35` autouse `offline`
  fixture removes `PIXABAY_API_KEY`, points `.env` and the search cache into `tmp_path`, and makes
  `stock.fetch` fail on any network use. `FakePixabay` (`conftest.py:44`) + `pixabay` fixture
  (`conftest.py:79`) fake search/download; helpers `make_image`, `write_script`, `scene`,
  `script_data`, `extract_frame`, `mean_volume`, `make_tone`. `needs_ffmpeg` skip marker
  (`conftest.py:21-22`). Smoke tests in `test_render_smoke.py` (format, silent track, edge-to-edge
  frame, box position, temp-file cleanup, locked target, typed errors), e.g.
  `def test_script_without_images_renders_with_stock_photos(tmp_path, pixabay, isolated_tmp)`
  (`test_render_smoke.py:322`). `test_stock_live.py` opt-in when a real key exists.
- **api** (`api/tests/`, pytest + `fastapi.testclient`): `conftest.py:35-44` session-scoped
  `engine` fixture runs `alembic downgrade base` + `upgrade head` on `TEST_DATABASE_URL` (skips if
  unset/unreachable); `db` fixture (`conftest.py:47-56`) wraps each test in an outer transaction
  with savepoints; `app` overrides `get_db`; `client_for(app)` sets `Origin`. Helpers `make_user`,
  `login`, `expire_all_sessions`. Example: `def test_list_shows_every_column_and_marks_me(client,
  me)` (`test_users.py:28`). Note: a worker process using its own DB connection would not see rows
  inside the test's uncommitted outer transaction.
- **web E2E** (Playwright 1.64.1, `web/playwright.config.ts`): starts its own api on 8100
  (`reels_e2e` DB, from `api/.venv`) and `next build && next start` on 3100; `workers: 1`.
  `e2e/helpers.ts:9` `resetDatabase()` runs `api/scripts/e2e_reset.py` (wipes `sessions`/`users`
  only — new tables must be added there, `e2e_reset.py:33-35`). No worker, Redis, FFmpeg, Pixabay
  or Claude in E2E today; CI web job does not install FFmpeg.
- Not covered anywhere: uploads, media serving, background jobs, Claude calls.

## 6. Shared Utilities

| Utility | Location | Purpose |
|---|---|---|
| `ApiError(status, code, message)`, `error_body` | `api/src/reels_api/errors.py:106,116` | `{code, message}` refusals |
| `current_session` / `current_member` | `api/src/reels_api/sessions.py:125,150` | auth dependencies |
| `get_db` / `get_engine` | `api/src/reels_api/db.py:143-151` | DB session per request, 5 s connect timeout |
| `config.read_env`, `database_url`, `allowed_origins`, `cookie_secure` | `api/src/reels_api/config.py` | env loading |
| `rules.RuleError`, `clean_name` (NFC) | `api/src/reels_api/rules.py` | shared input rules (API + CLI) |
| `parse_scene_text`, `normalize_text` | `worker/src/reels_render/markup.py:15,20` | `*red*` markup parse / validation |
| `layout_text`, `render_box`, positions | `worker/src/reels_render/textbox.py` | text box PNG + fit check |
| `normalize_image`, `is_image` | `worker/src/reels_render/images.py` | Pillow validation / EXIF fix |
| `build_timeline` | `worker/src/reels_render/timeline.py:133` | total length = sum of seconds (needs ≥ 2 scenes incl. title) |
| `ffmpeg.find_tools/run/probe` | `worker/src/reels_render/ffmpeg.py` | typed FFmpeg errors, stderr tail |
| `api<T>()`, `ApiError`, `formatLastLogin` | `web/src/lib/api.ts` | client calls, VN-time formatting |
| `EmptyPage`, `CenteredCard`, `AppShell`, `MeContext` | `web/src/components/` | UI shell pieces |

## 7. Potential Problems

- **Upload body buffering on Cloudflare (verified in node_modules):** OpenNext's edge converter
  reads every non-GET request body fully into memory —
  `Buffer.from(await event.arrayBuffer())` (`web/node_modules/@opennextjs/aws/dist/overrides/
  converters/edge.js:20-22`) — then the `fetch` proxy (`.../proxyExternalRequest/fetch.js`) forwards
  it to `API_URL`. Workers have a 128 MB memory limit and a Cloudflare-plan request body limit of
  100 MB (Free/Pro; 413 above). Photos and an mp3 per request are fine; the api should enforce its
  own per-file limits and uploads should be one file per request.
- **Response streaming:** the fetch proxy returns `response.body` as a stream with upstream status
  and headers (`fetch.js`), and Cloudflare enforces no response body limit; 10–30 MB MP4s stream
  through. Range headers are forwarded, so a Starlette `FileResponse` (FastAPI 0.162 / Starlette
  1.10 in `api/.venv`, Range-capable) can serve `<video>` seeking. Behaviour of 206 through
  OpenNext is not yet tested.
- **Next.js proxy body limit:** `proxyClientMaxBodySize` (default 10 MB) applies only to requests
  that pass through `proxy.ts`; its matcher (`proxy.ts:15`) excludes `/api/*`, so uploads are not
  cut — keep `/api` out of the matcher.
- **No `python-multipart`** in `api/pyproject.toml`; FastAPI `UploadFile`/`Form` will fail without
  it.
- **FastAPI direct `Response` drops the dependency's cookie header** (`fastapi/routing.py:750-753`
  vs `:790`): returning `FileResponse`/`StreamingResponse` means `current_session`'s refreshed
  `Set-Cookie` is not sent (session is still extended in DB; only the cookie max-age is not
  renewed). Harmless but surprising.
- **Shared storage between api and worker on Coolify:** separate Coolify applications each get
  their own volumes; api (uploads) and worker (reads uploads, writes MP4) need the same files —
  either a shared host-path bind mount on the same server, a Docker Compose resource with both
  services, or object storage (R2/S3, "could move later", architecture.md:52). Not configured
  anywhere today; Coolify setup steps are manual (README "Triển khai (CI/CD)").
- **Deploy pipeline covers one Coolify app:** `deploy-api` (`ci-cd.yml:110-140`) posts one
  `COOLIFY_WEBHOOK` and waits for `.deployments[0]`; a worker (and Redis) resource needs its own
  webhook/secret or a combined compose resource, and ordering (migrations run in api) matters.
- **Render runtime limits:** render budget ≤ 2× video length on the dev host (deployment.md:192);
  libx264 medium on a small VPS may be slower; long jobs must not be inside an HTTP request (a
  Cloudflare/proxy timeout would cut it).
- **Non-determinism:** auto stock picks are random per render (`stock.py:281`); the chosen stock
  image is not reported back, so "what the preview showed" ≠ "what the render used" unless the
  picked image is persisted as an Asset before rendering.
- **Title-scene stock search:** title is searched only with explicit `keywords`
  (`script.py:268-270`); a title without image and keywords → `MissingImagesError`.
- **Output path collisions:** `_publish` writes `.new.mp4` siblings if the target is locked; a
  server should use unique output paths per job to avoid `OutputNotReplacedError`.
- **Temp disk use:** each render's temp dir holds full-size stock downloads (≤ 15 MB each) and the
  `.tmp` output next to the target; Pixabay cache in `<system temp>/reels_render_cache/` is
  ephemeral in containers (acceptable: 24 h cache by terms).
- **Security:** uploads need type/size validation (Pillow `is_image` for photos; mp3 probing via
  `ffprobe`), server-generated file names (never user names in paths), auth on media GET
  endpoints, and no path from the client passed to `render_video`. FFmpeg already uses argv lists
  and `-i` inputs only (`graph.py:1-5`). Pixabay key is redacted in messages (`stock.py:210`).
- **Claude output validation:** model output must be checked against the script contract (text fit
  per scene, seconds ≥ 1, keyword length ≤ 100, ≤ 12-word uppercase titles that fit 5 lines at
  64 px) before it becomes renderable; otherwise `InputError` appears only at render time.
- **No rate limiting** anywhere in the api (web-app-auth code-research noted it); Claude and
  Pixabay calls cost money/quota.

## 8. Constraints & Infrastructure

- Python ≥ 3.12 for both packages; worker deps only `Pillow>=10` (`worker/pyproject.toml`); api
  deps fastapi, uvicorn, sqlalchemy 2, alembic, psycopg[binary] 3, pwdlib[argon2]
  (`api/pyproject.toml`).
- FFmpeg ≥ 4.3 filters only (architecture.md:94-95); `ffmpeg` and `ffprobe` must be on PATH
  (`ffmpeg.py:205-210`). Font bundled as package data (`worker/pyproject.toml` `fonts/*`,
  `textbox.py:10`), OFL licence in `fonts/OFL.txt`.
- Web: Next.js 16.4.3 (App Router; `web/AGENTS.md` warns the API differs from training data — read
  `node_modules/next/dist/docs/`), React 19.3, antd 6.6.8, `@opennextjs/cloudflare` 1.20.14,
  wrangler 4.155, Playwright 1.64.1. `open-next.config.ts`: no incremental cache. `wrangler.jsonc`:
  `nodejs_compat`, `global_fetch_strictly_public`.
- CI (`.github/workflows/ci-cd.yml`): `api` job = Postgres 17 service + pytest + `docker build`
  (`:21-49`); `worker` job = apt ffmpeg + pytest (`:51-66`); `web` job = Postgres + api venv +
  typecheck + Playwright + `opennextjs-cloudflare build` with `API_URL=https://api.invalid`
  (`:68-108`); deploy only on `main` after all three (`:110-165`). A worker Docker image is not
  built or deployed anywhere yet.
- Dev: `docker compose up -d postgres` only; api/web/worker run natively on Windows; use
  `127.0.0.1` not `localhost` (deployment.md:189-190). `.env.example` has `PIXABAY_API_KEY`,
  `DATABASE_URL`, `TEST_DATABASE_URL`, `ALLOWED_ORIGINS`, `API_URL`, `COOKIE_SECURE` only.
- UI rules (ux-guidelines.md): Vietnamese only, action-verb buttons ("Tạo kịch bản", "Render",
  "Tải MP4", "Chạy lại"), phone-width layout tested in E2E (`e2e/app.spec.ts:199`).
- Pre-commit hook (`.githooks/pre-commit`) only syncs `.claude/**` to Codex files.
- Storage growth: ~10–30 MB per video, no cleanup in MVP (deployment.md:260-261).

## 9. External Libraries / Platforms

- **Cloudflare Workers limits (Context7, developers.cloudflare.com/workers/platform/limits):**
  request body 100 MB on Free/Pro, 200 MB Business (413 above); no response body limit; 128 MB
  memory per isolate; CPU time default 30 s (Paid, raisable to 5 min) — proxied fetch wait is not
  CPU time.
- **OpenNext Cloudflare 1.20.14:** `defineCloudflareConfig` defaults `converter: "edge"`,
  `proxyExternalRequest: "fetch"` (`@opennextjs/cloudflare/dist/api/config.js:13-15`); external
  rewrites (`/api/*`) are proxied with global `fetch`, request body buffered, response streamed.
- **Next.js 16 `proxyClientMaxBodySize`** (`node_modules/next/dist/docs/.../proxyClientMaxBodySize.md`):
  10 MB default buffering limit for requests passing through proxy.
- **FastAPI 0.162 / Starlette 1.10** (installed in `api/.venv`): `UploadFile` needs
  `python-multipart`; `FileResponse` for downloads (`Content-Disposition` via `filename=`).
- **Pixabay API:** used via stdlib `urllib` (no SDK); see section 3.
- **Anthropic SDK:** not installed anywhere; model default `claude-sonnet-5-5` per docs.
