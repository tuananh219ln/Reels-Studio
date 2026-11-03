# Architecture

Status: built are the render core (see [Render Core](#render-core)), the web app with login and
user management (see [Web App and Auth](#web-app-and-auth)), and the video pipeline: topic →
Claude script → stored scene photos → server render, with the job queue and the worker service
(see [Video Pipeline](#video-pipeline)), with scene narration by ElevenLabs, the team music
library, prompts per topic group on `/knowledge`, posting to connected Facebook Pages (now or
scheduled) with the view-only post list and calendar, and the manual Affiliate Shopee product list.
The full Knowledge Base (documents, food bank) is agreed design and not yet built.

## Tech Stack

**Frontend:** Next.js (React, TypeScript). The UI needs a scene editor, image assignment, a job
log, and a post calendar. A Streamlit UI cannot support these for multiple users.

**Backend:** Python with a FastAPI API and a separate worker for long-running jobs.

**Database:** PostgreSQL for users, sessions, videos, scenes, jobs, and editable settings; Knowledge
Base tables are planned.

**Queue:** the `jobs` table in Postgres, not Redis: at 1–3 videos a day a separate queue service is
not worth running. Long-running work never runs in the API process: renders and Claude script
generation run in the worker (Knowledge Base drafting will too).

**Rendering:** Python builds an FFmpeg filter graph:

- `zoompan` creates the Ken Burns motion.
- `overlay` places the text, followed by transitions and the audio mix.
- Pillow pre-renders text boxes as transparent PNGs.

**Rationale:**

- **Reference pipeline:** the pipeline stages follow
  [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (MIT).
- **Own repository, not a fork:** MoneyPrinterTurbo carries many unused providers, OAuth flows,
  and a Streamlit UI. It also has no auth, no database, no scene model, and uses stock video clips
  instead of photos.
- **No MoviePy compositing:** MoviePy composites frames in Python and is the speed bottleneck. A
  native FFmpeg filter graph is faster, and porting the backend to Go would add no further speed.
- **No Remotion:** Remotion needs a paid Company License for teams of 4 or more people.

## Components

In development `docker-compose.yml` runs only `postgres`; `web`, `api`, and the worker run
natively. In production `api`, the worker, and `postgres` run on Coolify and `web` on Cloudflare
Workers (see [deployment.md](deployment.md#production)).

| Component | Responsibility |
|---|---|
| `web` | Next.js UI. Calls the API only. |
| `api` | FastAPI app ([api/](../api/)). Auth, videos, scenes, photo and MP3 uploads, the music library, stock search and picker for scene photos (Pixabay, Pexels, Openverse), previews, file serving, `/knowledge` settings, the job log. Enqueues jobs. |
| worker | Same `reels_api` package, started as `python -m reels_api worker`. Runs jobs: script writing and cloning (Claude), AI photos for scenes that have none (Gemini), renders (ElevenLabs narration, then FFmpeg), narration alone for the preview ("Tạo giọng thật", reused by the next render), and posting to the Facebook Page and taking posts off it. |
| `postgres` | Relational data and the job queue. |
| storage | One folder of uploaded photos, MP3s (music, narration, and library tracks under `music/`), thumbnails, and MP4s, shared by the api and the worker (`STORAGE_DIR`). |

The api and the worker are one Python package so models, migrations, and database configuration
exist once; `reels_render` stays a library that needs only Pillow. Both images also install
`reels_render`, because the api draws previews and checks scene text with the renderer's own code.
Files go through a small storage layer ([storage.py](../api/src/reels_api/storage.py));
only a folder backend exists, chosen so an S3/R2 backend can be added later without touching video,
scene, or job logic.

**Render pipeline:** every scene photo is chosen by a member while editing (uploaded, picked from the stock grid, or found by "Tìm ảnh") and stored, so the render uses exactly the photo the preview showed. A photo cropped in the editor ("Chỉnh khung") is cut to 9:16 in the browser and stored in place of the old one by `POST /scenes/{id}/image/crop`, which validates it like an upload but keeps the scene's `image_source`, so an AI photo stays `ai:<model>`; the render needs no crop settings. The
worker then:

1. Makes the narration each scene still lacks (see [Narration](#narration)), then checks the total
   length again, because narration lengthens scenes.
2. Copies the stored photos, narration MP3s, and the optional music MP3 into a work folder.
3. Renders the text overlay PNGs.
4. Composes everything in a single FFmpeg filter graph with the music and narration, producing a
   9:16 MP4.

Code adapted from MoneyPrinterTurbo modules (voice, material search) keeps its MIT
attribution.

### Render Core

Steps 2–3 of the render pipeline are the Python package `reels_render` in
[worker/](../worker/), with a thin CLI (`python -m reels_render script.json -o out.mp4
[--music …] [--music-volume …]`). The worker calls the same callable `render_video`, which raises
typed errors (subclasses of `RenderError`) whose Vietnamese messages go into the job log.

- **Script input:** a JSON file with a title scene and content scenes, each with `text` and
  `seconds`, plus optional `image`, `keywords`, and `voice` (a narration audio file). Image paths are relative to the JSON file.
  `keywords` is a list of Vietnamese search terms, most specific first. See
  [samples/xuong-khop.json](../samples/xuong-khop.json).
- **Missing image means stock search (CLI path).** A scene whose `image` is empty, absent, or
  points to a missing file (with a warning) gets a Pixabay photo, searched by its `keywords` or, for
  a content scene without them, by its first text line. The title scene is searched only when it
  has `keywords`. The choice is random among the first three unused results, so re-renders vary.
  Stock photos live in the render's temp folder and are never written to the JSON. No source or
  license info is stored, by the owner's decision. The server render never reaches this path: it
  passes stored photos and no keywords.
- **Nobody to ask means an error.** `render_video` never reads the keyboard. A scene still without
  an image raises `MissingImagesError`; key, network, and rate-limit problems raise
  `StockSearchError`. Only the CLI, in a terminal, asks the user to drag an image in, copies it
  next to the script, and writes its path into `image`.
- **The title scene has its own image and length.** It never borrows scene 1's image. In the
  database it is a scene row marked as the title scene, 3 seconds by default.
- **Empty text means no text box.** The filter graph still gets a box input, a transparent pixel,
  so every scene keeps one image and one box.
- **Validation runs before FFmpeg.** The output is written to a temp file next to the target and
  replaced only after a successful render.
- **FFmpeg safety:** every file is passed with `-i` and referenced by stream label, never written
  into the filter graph. FFmpeg is called with an argument list, not a shell.
- **FFmpeg compatibility:** use only filters and options available since FFmpeg 4.3. The worker
  image uses Debian's FFmpeg package (7.1 at the time of writing), and CI runs the render parity
  test inside that image.
- **Audio bed:** without music the video still gets a silent track. Narration is one track as long
  as the video, built per scene from exact sample counts (narration delayed 0.2 s past the
  crossfade, padded with silence), and added to the bed with `amerge` + `pan` at full level.
- **Narration lengthens its scene:** a scene lasts at least 0.2 s + the narration + 0.4 s, rounded
  up to a tenth of a second (`timeline.fit_seconds`); its `seconds` are the minimum.
- **Font:** Be Vietnam Pro Black (OFL) is bundled in the package, not installed per machine.

### Scene Video Clips

A scene may hold an uploaded video clip instead of a photo
([clips.py](../api/src/reels_api/clips.py)). The UX rules are in
[ux-guidelines.md](ux-guidelines.md#video-scenes).

- **Upload:** one file per request to the scene. MP4/MOV and WebM, with H.264, HEVC, or VP9 video,
  1–60 s long, at least 720 px on the short side and at most 4096 px on the long side, up to
  50 MB. The web worker on Cloudflare holds the whole request in memory (128 MB) and Cloudflare
  refuses requests over 100 MB, so the limit stays well below both. The upload is spooled to a
  temp file, never held in memory, and checked before any row is locked.
- **Container from the bytes:** `ftyp` at byte 4 means MP4/MOV and is forced with `-f mov`. The
  EBML header means WebM and is forced with `-f matroska`. Anything else is refused before
  FFmpeg runs, so a playlist or concat file can never make FFmpeg open other files. `ffprobe`
  and frame extraction run with an argument list and a 30 s timeout, which is why the api image
  installs Debian's FFmpeg, as the worker image does. Every video stream in the file must pass the
  codec and size checks, and the preview frame is taken from the first one (`-map 0:v:0`), as the
  render does. A huge extra stream therefore can never be decoded in the api. Headers can still
  lie (an H.264 stream may switch to a huge size partway through), so both the preview frame grab and
  the render pass `-max_pixels` (4096×2304) before the clip's `-i`. The decoder then refuses larger
  frames instead of allocating gigabytes.
- **Stored data:** the scene's `video_key`, `video_seconds` (the video stream's own length,
  because the container's is the longest stream, often a longer audio track), `video_start` and
  `video_speed` (0.5–2, migration 0022; every older scene is 1).
  Uploading a clip clears the photo, uploading or choosing a photo clears the clip, and the
  replaced file is deleted after the commit. A new clip starts at 1× and sets the scene's seconds to its length
  minus the 0.2 s it plays into each crossfade (one for the title, two for a content scene), in
  tenths, between 1 and 10 s. The start time must leave at least 1 s of clip. A clone rewrites every scene, so it
  starts without the source's clips.
- **Trim:** the editor's "Cắt video" dialog picks a start, an end and a speed on the clip and saves
  `video_start`, `video_speed` and `seconds` in one `PATCH /scenes/{id}`, with the seconds the part
  divided by the speed, less its crossfades; the api checks them as for typed values.
- **Speed:** `seconds` stays the scene's length on screen. The scene takes
  (seconds + crossfades) × speed of the clip, since the crossfades play at that speed too. The
  start time's limit does not change with the speed: a part past the clip's end only warns.
- **Preview:** the scene preview and, for the title scene, the thumbnail are drawn from the
  clip's frame at the start time, taken with the same input seeking as the render. The editor
  plays the stored clip through the login-protected `/api/scenes/{id}/video` endpoint.
- **Text box place:** a scene may carry `text_position` ([x, y], the box centre); `textbox.place_box`
  centres the box there inside `SAFE_ZONE` (the title only moves up and down), and without it the box
  sits where the template puts it. The api writes each scene's effective place (its own, else the
  video's for content scenes) into the script and into the MP4 signature only when there is one.
- **Script input:** a scene has `video` (path relative to the JSON), `video_start` and optionally
  `video_speed` (0.5–2, default 1) instead of `image`. A scene with both is a validation error, and
  stock search never runs for a clip scene.
- **Filter graph:** the clip is passed with `-ss <start>` before its `-i`. Its chain replaces the
  photo chain: `setpts=PTS-STARTPTS,fps=30,scale=1080:1920:force_original_aspect_ratio=increase:out_range=tv,
  crop=1080:1920,format=yuv420p,setsar=1,tpad=stop_mode=clone:stop_duration=<clip seconds>,
  trim=end_frame=<clip frames>,setpts=PTS-STARTPTS`.
  - It has no `zoompan` and no prescale.
  - At a speed other than 1× the first filter is `setpts=(PTS-STARTPTS)/<speed>`; at 1× the graph
    is unchanged. The clip's sound is never used, so no audio filter is needed.
  - `fps` comes right after it, so variable-frame-rate phone footage, and a clip at any speed,
    becomes constant 30 fps.
  - `tpad` holds the last frame when the clip ends early, and `trim` cuts the clip to the
    timeline's exact frame count, so crossfade offsets stay frame-exact.
  - The clip's audio stream is never referenced.
- **Checks:** a missing clip blocks the render, as a missing photo does. A scene that needs more
  than the clip left after its start only warns. The scene's length counts its narration plus
  0.2 s for each crossfade next to it, times its speed.
- **Fingerprint:** the clip's key and start time join the MP4 fingerprint only for a scene with a
  clip, and its speed only when not 1×, so MP4s rendered before clips or speeds existed stay current.
- **Not handled:** HDR footage (iPhone HEVC HLG) is converted without tone mapping, so it looks
  washed out. Members should film in SDR.

## External Integrations

| Service | Use | Notes |
|---|---|---|
| LLM (Claude and other providers) | Script generation and cloning (built); drafting Knowledge Base content (planned) | Called only from the worker ([llm.py](../api/src/reels_api/llm.py)), with the provider the team chose on `/settings/ai`. Claude goes through the Anthropic SDK (default model `claude-sonnet-5-5`, with the server-side refusal fallback enabled); OpenAI, Gemini, DeepSeek, OpenRouter, Groq, xAI, Qwen, Ollama and a custom provider go through the OpenAI-compatible `POST {base URL}/chat/completions` with one user message and no `max_tokens`. An answer cut off by the model's length limit fails the job at once instead of being asked again. "Kiểm tra kết nối" calls `GET /models` (no tokens) from the api. Every call is logged with the provider, model and token counts. With nothing set on the page, Claude is used with `ANTHROPIC_API_KEY` / `CLAUDE_MODEL`. Knowledge drafting will use web search so it can return source URLs. |
| ElevenLabs | Scene narration in the render job | The premade "Adam" voice by default, model `eleven_v3` with `language_code: vi` (`eleven_multilingual_v2` does not speak Vietnamese). Voice and model are configurable; the key comes from Cài đặt › Nguồn tư liệu (encrypted, `source_keys.py`) or else `ELEVENLABS_API_KEY`. Paid per character, so each scene's MP3 is stored and reused. |
| Facebook Reels Publishing API | Posting a video to the team's one Page | Called only from the worker ([facebook.py](../api/src/reels_api/facebook.py)). Pages are connected on `/fanpages` by pasting a token, so there is no OAuth screen. A user or system user token is swapped for each Page's own token through `/me/accounts`, and that token is what is kept. Once the reel is live or scheduled, the publish job sets its cover to the first frame of the MP4 it holds (the title scene) with `POST /{video_id}/thumbnails` (`source`, `is_preferred=true`); a cover that cannot be made or is refused is only logged, and Facebook keeps the frame it picked. |
| Stock photos (Pixabay, Pexels, Openverse) | The web editor's "Chọn từ kho ảnh" picker switches between three sources: Pixabay (the default; keys of Pixabay, Pexels and Gemini come from Cài đặt › Nguồn tư liệu, encrypted, or else `.env`, see `source_keys.py`), Pexels (vi-VN locale, portrait; offered only when it has a key) and Openverse (no key needed; optional registered OAuth credentials raise its rate limits; CC0 and public-domain-mark works only, filtered in the query and again per result). The picker opens each source in the language it indexes: the scene's English terms for Pixabay/Pexels, its Vietnamese terms for Openverse. "Tìm ảnh" takes the next result from one source, Pixabay unless the member picks another from the arrow beside it (`POST /scenes/{id}/find-image?source=`), reading the keyword list in that source's language with the other list as fallback; the CLI's stock search stays Pixabay-only. A chosen photo from any source is re-checked against that source's results (searched with the same orientation), downloaded by the api and stored with the scene, like an upload; the grid's thumbnails are only shown. Filters (`orientation` = vertical by default, square or all; `hide_used`): each source is asked for the shape where it can (Pixabay `orientation=vertical`, Pexels `portrait`/`square`, Openverse `aspect_ratio=tall`/`square`) and results whose size is known are checked again by shape and dropped when the served file's short side is under 640 px; photos another scene of the video shows (by `image_source`) are hidden, and "Tìm ảnh" never picks one. Pixabay's search cache is kept per keyword and orientation. A Cloudflare bot-check page in front of Pixabay (HTML instead of the API's text) is reported as the network being blocked, not as a rate limit. After a script or clone job, a `photos` job ("Tự tìm ảnh", [auto_photos.py](../api/src/reels_api/auto_photos.py), on unless the team turned it off on Cài đặt › Nguồn tư liệu) gives every scene without a photo or clip one stock photo with the same rules (tall, big enough, never one another scene shows; Pixabay, Pexels, Openverse in that order, skipping sources turned off, without a key or failing in that job), stored with `scenes.image_auto` until a member changes or keeps it; it never makes AI photos and fails only when every source failed |
| Photos from any site (pasted link or dragged photo) | "Dán ảnh/link", a drop from another tab, "Tìm trên Google" (only opens Google Ảnh in a tab) | `POST /scenes/{id}/image-from-url` ([remote_images.py](../api/src/reels_api/remote_images.py)) downloads the link inside the request: http(s) only, the host must resolve to public internet addresses and every connection, redirects included, is checked against the address it reached; 15 MB, 15 s, then the upload checks. The link is stored as `image_source`. A copied photo or a `data:` thumbnail is uploaded by the browser through the normal photo upload. The member chooses the photo and is responsible for it, as for an upload; no Google API is used. |
| Stock video clips (Pexels Videos, Pixabay Videos) | The picker's "Video" mode | Searched by the api ([stock_clips.py](../api/src/reels_api/stock_clips.py)) with the same keys as the photos; Pexels asked for portrait clips. Of each clip's files the one closest to 1080 px wide is offered. A chosen clip is named by its id, searched again, downloaded (at most 50 MB) and stored like an uploaded clip, so the render never fetches anything. |
| Gemini (Google AI Studio) | AI photos for scenes that have neither a photo nor a clip, in the `image` job | Called only from the worker ([imagegen.py](../api/src/reels_api/imagegen.py)), from the scene's `image_prompt` (written in English by the script, the title scene's from `title_image_prompt`; a title scene without one: its first line of text), followed by the team's shared style ([image_style.py](../api/src/reels_api/image_style.py)). The model is configurable; the default is `gemini-2.5-flash-image`, asked for a 9:16 frame. The bytes pass the upload checks before they are stored with `image_source` = `ai:<model>`, and every call is counted on the job like the script job counts Claude. A refused prompt fails only its scene; a missing key or an exhausted quota fails the job and keeps the scenes already done. | Free for commercial use; no attribution is shown anywhere, which is why Openverse is limited to works without conditions. Pixabay API terms: download images that are used (no hotlinking) and cache search results for 24 hours (under the system temp folder). Searches inside a request give up after about 10 seconds. |
| Cloudflare Workers AI | AI photos, the second provider of the `image` job, beside Gemini. The provider is fixed on the job when it is queued (`jobs.image_provider`): the one a member picked from the button's arrow, else the team's default ([image_providers.py](../api/src/reels_api/image_providers.py): chosen on Cài đặt › Nguồn tư liệu, else `IMAGE_GEN_PROVIDER`, else Cloudflare when it is set up, else Gemini). Running out of Cloudflare never switches to Gemini by itself. | Called only from the worker ([imagegen.py](../api/src/reels_api/imagegen.py)): REST `POST /accounts/{account}/ai/run/{model}` with a Bearer API token (from Cài đặt › Nguồn tư liệu or `IMAGE_GEN_CF_API_KEY`) and `IMAGE_GEN_CF_ACCOUNT_ID`; default model FLUX.1 schnell (`@cf/black-forest-labs/flux-1-schnell`, 4 steps). It ignores width/height and answers a 1024×1024 square, which imagegen cuts at the centre to 9:16 (JPEG) before the same upload checks; `image_source` = `ai:<model>`. The free allowance is 10,000 neurons a day (about 57 photos), reset at 00:00 UTC; running out or a bad token fails the job, a refused prompt fails only its scene. | FLUX.1 schnell is Apache-2.0; no SynthID watermark. |
| FFmpeg | Rendering | Installed in the worker image from Debian's package ([api/Dockerfile.worker](../api/Dockerfile.worker)); on the dev host installed natively (see [deployment.md](deployment.md#current-state)). |

Later phases add the Instagram, YouTube, and TikTok publishing APIs.

## Data Flow

1. A member enters a topic; the API creates a draft video and a script job.
2. The worker calls the team's LLM (Claude unless another provider is chosen on `/settings/ai`) with the editable script prompt and the banned words (see
   [content.md](content.md#script-generation-contract)), and saves the script.
3. Members give every scene a photo or clip (upload, or a stock photo the api stores); "Tạo ảnh AI cho cảnh thiếu" instead runs an image job that generates the missing photos with the AI image provider and stores them the same way; "Tạo ảnh AI" on one scene's card runs the same job for that scene only (`jobs.scene_id`), replacing its photo or clip, and any failure there fails the job while the scene keeps what it had. Members then edit the script, music, and post texts; each field saves on its own.
4. "Render" enqueues a render job after the pre-render checks pass.
5. The worker renders the MP4 from the saved data into storage and records it on the video.
6. The video page plays and downloads the MP4; `/jobs` lists every job.

## Data Model

Built (migrations in [api/migrations/](../api/migrations/), models in
[models.py](../api/src/reels_api/models.py)):

| Table | Key contents |
|---|---|
| `users`, `sessions` | Members and their login sessions (see [Web App and Auth](#web-app-and-auth)). |
| `videos` | Topic, whether the script exists, narration on/off, its own settings (`options`: voice, reading speed as a tempo factor, voice level, ducking, transition, motion, zoom, text style, captions; empty for older videos, which render the original template, see [video_options.py](../api/src/reels_api/video_options.py)), title options, caption, hashtags, affiliate suggestions, pinned comment, self-review notes, music suggestions, optional MP3 with volume, the current MP4 with its length, render time and render fingerprint, thumbnail, the clone snapshot for a cloned draft, creator. |
| `knowledge_topics` | One topic group of `/knowledge`: unique name, script prompt, clone prompt, banned words. Empty until written. A video points to one; it cannot be deleted while videos do. Replaced the `settings` rows, which stay unread so a rollback finds them. |
| `scenes` | Belongs to a video; the title scene or a content scene, order, seconds, on-screen text with `*red*` markup, voice text, Vietnamese and English stock-search keywords, image prompt, the stored photo and where it came from (upload, `ai:<model>` for a generated one, or the stock photo's URL), the reason a photo is missing, the optional clip with its length and start time, the last narration MP3 with its length and the signature it was made from, and where a member dragged its text box (`text_x`, `text_y`, the box centre; null: the video's place in `videos.options.text_position`, else the template's). Whether its photo is the app's unchecked pick (`image_auto`). |
| `fanpages` | A connected Facebook Page: its id and name, the Page's encrypted token and its last characters, in use or stopped, who changed it last. |
| `publications` | One post of a video to a platform (only `facebook` today); a video posted again has one row per post, at most one of them pending: the Fanpage, pending, scheduled, published, cancelled (never public) or deleted (taken off the platform after going public), the scheduled time, the platform's id of the post and the MP4 sent, who started it, who cancelled or deleted it and when (nobody when a check found it so on Facebook), when Facebook was last checked (`checked_at`). |
| `jobs` | Belongs to a video; kind (script, clone, render, publish, unpublish: takes the post `publication_id` off Facebook; check: reads that post on Facebook and records what it says; image, photos: the "Tự tìm ảnh" queued after a script or clone; voice: "Tạo giọng thật" in the preview, the narration a render would make and nothing else; an image job may name one scene, `scene_id`, and its provider, `image_provider`), status (queued, running, done, failed, cancelled), who started it, timings, Vietnamese error plus technical detail, number of LLM calls (`claude_calls`, named for the first provider) and of Gemini image calls, the provider and model a script or clone job wrote with, the job it retries. At most one queued or running job per video. |
| `settings` | The prompts and banned words before `knowledge_topics`; no longer read. |
| `llm_providers` | One row per provider set up on `/settings/ai` (the list itself is fixed in [llm.py](../api/src/reels_api/llm.py)): base URL and model (empty means the provider's default), the API key encrypted like a Fanpage token ([crypto.py](../api/src/reels_api/crypto.py)) and its last characters, who changed it last. |
| `app_settings` | Team-wide settings from the Cài đặt pages by key: `llm_provider` (the provider that writes scripts; Claude when unset), `video_defaults` (what a new video's settings, narration switch and music level start as), `stock_sources_off` (stock sources the team turned off). |
| `music_tracks` | The team music library: name, topics and one mood (each from a fixed list in [routes_music.py](../api/src/reels_api/routes_music.py)), source/license note, the stored MP3, who added it. Choosing a track for a video copies the file into the video's folder, so editing or deleting the track never changes a video or its render. |
| `affiliate_products` | The team's Shopee products, typed in from the affiliate dashboard: topic group, name, link, shop, shop type, rating, sales, price, commission rate, draft or approved, who approved it and when, creator. Approval needs a trusted shop type, at least 4.7 stars, 100 sales, and no banned word in the name ([routes_affiliate.py](../api/src/reels_api/routes_affiliate.py)); changing an approved row sends it back to draft. A topic group with products cannot be deleted. |
| `video_presence` | Who has a video open: one row per open video page (`tab`, a random id the page picks), the member, whether that page is in "Chỉnh sửa", and when it last reported. Rows silent for 30 s are deleted at the next report ([routes_presence.py](../api/src/reels_api/routes_presence.py)); deleted with the video or the user. |
| `video_affiliate_products` | The products attached to a posted reel; deleted with either side. Only an approved product that meets the rules can be added; one that later stops qualifying stays, flagged, and is left out of the copied comment. |

Files are not table rows: a video's files live under one storage folder per video, with
server-generated names (retention: [deployment.md](deployment.md#operations)).

Planned:

| Entity | Key contents |
|---|---|
| KnowledgeDoc | one per knowledge document type; editable content (no approval state) |
| FoodItem | food, main nutrients, benefits, who should avoid it, source URLs, `draft` / `approved` status |
| Video additions | content language (`vi` now, `en` later) |

## Video Pipeline

- **Jobs and the worker** ([worker.py](../api/src/reels_api/worker.py),
  [jobs.py](../api/src/reels_api/jobs.py)):
  - Only one worker takes jobs: it holds a Postgres advisory lock for its whole life. During a
    deploy the new container waits until the old one has exited, then takes over.
  - Jobs are claimed one at a time, oldest first; "Hủy" works only on a queued job and waits for a
    claim in progress.
  - Each job runs in its own child process and process group. After 15 minutes the worker kills
    the whole group (including FFmpeg) and marks the job failed; the next job runs without a
    restart.
  - A job still marked running when a worker starts belonged to a worker that died: it becomes
    failed ("Worker khởi động lại giữa chừng") and is never re-run automatically, to avoid
    unplanned Claude spending. Members press "Thử lại", which always creates a new job.
  - Retrying a script or clone job whose script was saved does nothing: no new Claude call, no
    overwritten edits.
  - The worker waits instead of crashing while the `jobs` table does not exist yet.
- **Locking and saving:** a video with a queued or running job cannot be edited or deleted; the
  database allows only one such job per video. Every change locks the video row, so edits and new
  jobs for one video happen one after another. Each field saves on its own, so two members editing
  different fields never overwrite each other; on the same field the last save wins.
- **Pre-render checks** ([script_rules.py](../api/src/reels_api/script_rules.py)) block
  only real errors (missing photo, text the renderer would refuse or that overflows its box, scene
  length outside 1–10 s, total over 90 s, no content scene) and only warn about departures from the
  channel formula and banned words. Text checks and previews use the renderer's own text-box code,
  so what passes here renders there.
- **Previews and thumbnail:** a scene preview is the photo cover-cropped to 1080×1920 with the
  renderer's text box and the MP4's colour subsampling, so the title-scene preview matches the
  MP4's first frame. The video thumbnail is the title-scene preview, redrawn whenever its photo
  or text changes.
- **"MP4 chưa cập nhật":** each render stores a fingerprint of what changes the MP4 (scene texts,
  seconds, photos, order, MP3, volume, narration). The label shows when the current data no longer matches;
  captions, hashtags, keywords, and image prompts do not affect it. A failed or cancelled re-render
  keeps the previous MP4.
- **Narration** ([tts.py](../api/src/reels_api/tts.py)): Claude writes a voice text per
  scene (the title scene too); members edit it, and one switch per video turns narration off. A
  scene reads its voice text only; with an empty voice text it reads its on-screen text, cleaned for
  speech (`videos.screen_speech`: no markup or list number, each line a sentence; the title scene
  whole), and with neither it is silent. The api sends this as `spoken_text`, which the preview reads
  too. The render job calls ElevenLabs only for a scene whose stored MP3 was made from a
  different spoken text, voice, or model, and commits each MP3 at once, so a retry or re-render
  pays only for what changed; editing the on-screen text remakes the narration only of a scene that reads it. Once made, the scene card plays it and shows the lengthened scene. Narration not made
  yet cannot be measured, so a total over 90 s is caught by the render job after it is made.
- **Posting to Facebook ("Đăng lên Facebook"):**
  - The `publish` job uploads the current MP4 with the saved caption and hashtags. An MP4 out of date
    with the edits is refused, and so is an MP4 the chosen Page already holds. A new render, or the
    same MP4 after its post was cancelled or deleted, makes a new `publications` row.
  - Scheduling uses Facebook's own scheduling, so the file is uploaded at once, the worker has no posting
    timer, and a later re-render never changes what was scheduled. Facebook then publishes by itself,
    so the app counts a scheduled post as published once its time has passed. Changing the time is
    done in Meta Business Suite.
  - **Checking a post against Facebook.** Nothing tells the app about a change made in Meta Business
    Suite or a reel Facebook drops, so a `check` job reads the reel and records what Facebook says:
    live (published, or scheduled with Facebook's time), or closed, as with "Xóa", deleted if it may
    have been public, else cancelled, with nobody as who closed it. One still processing is left as
    it is, and the check never changes anything on Facebook. The worker queues one check of each
    scheduled post 10 minutes after its time (`queue_post_checks`, looked for every minute), once per
    scheduled time even if it fails, and not while the video has a job; a member queues one any time
    with "Kiểm tra", `POST /api/posts/{id}/check`, for a scheduled or published post.
  - **"Hủy đăng" and "Xóa"** are one endpoint, `POST /api/posts/{id}/take-down`. A post Facebook never
    received (no `remote_id`) becomes cancelled in the request, its queued `publish` job cancelled.
    Any other queues an `unpublish` job, also replacing a queued `publish` job; a running job refuses
    with 409. The job reads the reel's status and deletes it (`DELETE /{video-id}`), and ends the post
    as deleted if the reel was ever public, else cancelled. A reel Facebook no longer has counts as
    gone. A status read or delete that fails fails the job and leaves the post as it was.
  - **Never a second post by accident.** The reel's id and its MP4 are saved before the upload, and the moment
    Facebook is asked to publish is saved before asking. A retry reads the reel's status first,
    because an attempt may have reached Facebook whatever it reported. A live reel needs nothing,
    and the app records what Facebook says. One Facebook was asked to publish and is still
    processing is waited for. A reel holding the current MP4 is finished again; whether a second
    finish is harmless is assumed, because the docs do not say. A new reel is made only when the old
    one is gone (HTTP 404), refused, or not fully received, or when it holds an older render and
    was never asked to publish, or was asked over 30 minutes ago. A status read that fails or says
    nothing fails the job and posts nothing.
  - The job repeats the MP4 and time checks, because "Thử lại" skips the endpoint.
  - The job locks the video like a render, for the minute or so it takes.
  - `GET /api/posts` ([routes_posts.py](../api/src/reels_api/routes_posts.py)) reads
    scheduled, published, cancelled and deleted rows for `/posts` and `/calendar`, with the video's
    `thumbnail_url` and `busy` while the video has an active job. Pending posts are left out. The calendar loads every row, keeps the
    scheduled and published ones and groups them in the browser, which is enough at 1–3 videos a day.
- **Clone ("Nhân bản"):** stores a snapshot of the source as edited at that moment plus the change
  request on the new draft, and copies the source's MP3 as the draft's own file. The source is not
  locked. Cancelling and writing the draft again reruns the same clone.
- **Files:** every file endpoint (photos, previews, thumbnail, MP3, MP4) requires login; the MP4
  supports Range requests for seeking. Uploads are one file per request with api-side limits
  (photos JPG/PNG/WebP up to 15 MB and 24 megapixels; MP3 up to 20 MB, checked by its first bytes;
  scene clips up to 50 MB, see [Scene Video Clips](#scene-video-clips)).
  No path from a client ever reaches the renderer.

## Web App and Auth

- **Layout:** `web/` is Next.js 16 (App Router, TypeScript) with Ant Design (the orange of
  the app's icon, see the theme in [ux-guidelines.md](ux-guidelines.md#app-look)); `api/` is FastAPI with SQLAlchemy 2, psycopg 3, and Alembic. Each manages its own
  dependencies, like `worker/`.
- **One origin:** the web app calls the API through the Next.js rewrite `/api/*` → `API_URL`, so
  the session cookie is first-party and the API needs no CORS. `web/src/proxy.ts` redirects app
  pages to `/login` before rendering when there is no session cookie; the API validates the session
  on every request.
- **Login:** email + password only. There is no self-signup. Google login is planned ([#54](https://github.com/tuananh219ln/Reels-Studio/issues/54)). The CLI
  `python -m reels_api create-user` creates the first user and is the
  recovery path: for an existing email it resets the password, re-enables the account, and signs out
  all its sessions.
- **Sessions:** an opaque random token in an `httpOnly`, `SameSite=Lax` cookie, `Secure` when
  `COOKIE_SECURE` is set (production). Postgres stores only
  its SHA-256 hash. Sessions last 30 days and slide on every request. They live in the database,
  not in a JWT, so disabling a user, setting a temporary password, changing a password, and "sign
  out of all devices" take effect immediately.
- **Users are disabled, never deleted,** and can be re-enabled. Nobody can disable themselves, and at
  least one active user always remains. Disabling locks all active user rows, so two people disabling
  each other at once cannot both succeed.
- **Temporary passwords** (set when adding a user or by a teammate) force a password change. The
  API itself blocks everything except `GET /api/me`, the password change, and logout until then.
- **Who is on a video:** an open video page reports itself every 10 s with
  `POST /api/presence/videos/{id}` (`tab`, `editing`) and gets back the other members who have
  the video open, one entry per member (editing if any of their tabs is); it says
  `POST /api/presence/videos/{id}/leave` when it closes, and a page that stops reporting drops out
  after 30 s. It is information only: nothing is locked, and two members can still edit at once.
- **CSRF:** POST/PUT/PATCH/DELETE must carry an `Origin` listed in `ALLOWED_ORIGINS`.
- **Errors:** refusals return `{code, message}` with a Vietnamese message. A database outage returns
  503 `database_unavailable`. Login failures use one generic message, and "account disabled" is
  shown only after a correct password.

### ChatGPT MCP connection

The optional private MCP endpoint uses member-authorized OAuth delegation, stateless Streamable
HTTP, and the official MCP Python SDK. The web forwards its two exact `.well-known` discovery
paths; `/api/mcp` stays behind the same origin as browser consent. Its bearer credentials do not
work on the normal cookie API, and cookies alone never authenticate MCP. Only the four exact
server protocol POST paths bypass Origin checks; browser consent and revocation keep them.

`mcp_clients` stores registered ChatGPT callback clients; `mcp_authorizations` holds short-lived
session-bound consent tickets and single-use PKCE codes; `mcp_connections` holds scopes,
resource binding, hashed rotating credentials and expiration. Session foreign keys cascade when
the underlying browser login is revoked. Token validation also checks the user's active and
password-change state on every request and tool call.

The tools call the existing video handlers directly, with the authenticated member, storage and
database session. They do not call the HTTP API with manufactured cookies or duplicate business
rules. Long work still queues the existing script/render jobs. No publishing, deletion, secret
or account-management tools are exposed. Setup, boundaries and verification: [chatgpt.md](chatgpt.md).

### Sensitive Data

- API keys (Anthropic, Pixabay, Pexels, ElevenLabs, Gemini) live only in environment variables. They are never
  committed or stored in the database.
- Facebook Page tokens are pasted on `/fanpages`, by the owner's decision, checked with Facebook,
  and stored in `fanpages` encrypted with a key generated in the storage folder
  ([fanpages.py](../api/src/reels_api/fanpages.py)), so a database dump alone does not
  reveal them. No response ever carries one, only its last four characters. Any member can replace
  one. Losing the key file only means pasting the tokens again.
- Passwords are stored hashed.
- The only personal data is team members' emails.
