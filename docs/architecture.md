# Architecture

Status: built are the render core (see [Render Core](#render-core)), the web app with login and
user management (see [Web App and Auth](#web-app-and-auth)), and the video pipeline: topic →
Claude script → stored scene photos → server render, with the job queue and the worker service
(see [Video Pipeline](#video-pipeline)), with scene narration by ElevenLabs, the team music
library, prompts per topic group on `/knowledge`, posting to connected Facebook Pages (now or
scheduled) with the view-only post list and calendar, the Affiliate product list (Shopee and TikTok Shop,
with Shopee's API searching and making each Page's links), and TikTok versions posted by hand.
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
| worker | Same `reels_api` package, started as `python -m reels_api worker`. Runs jobs: script writing, cloning and learning from a sample video (Claude), AI photos for scenes that have none (Gemini), renders (ElevenLabs narration, then FFmpeg), narration alone for the preview ("Tạo giọng thật", reused by the next render), and posting to the Facebook Page and taking posts off it. Between jobs it reads the posts' numbers on Facebook ([metrics.py](../api/src/reels_api/metrics.py)) and checks each connected Page's token ([fanpages.py](../api/src/reels_api/fanpages.py)). |
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
  test inside that image. The other CI jobs use a static FFmpeg 7.1.1 build
  (`.github/actions/setup-ffmpeg`), cached between runs.
- **Audio bed:** without music the video still gets a silent track. Narration is one track as long
  as the video, built per scene from exact sample counts (narration delayed 0.2 s past the
  crossfade, padded with silence), and added to the bed with `amerge` + `pan` at full level.
- **Narration lengthens its scene:** a scene lasts at least 0.2 s + the narration + 0.4 s, rounded
  up to a tenth of a second (`timeline.fit_seconds`); its `seconds` are the minimum. A scene whose seconds follow
  its narration ("Tự khớp lời đọc") is given 0.2 s + the narration + the video's "Nghỉ sau lời đọc"
  (`options.voice_pause`: 0.4, 0.7 or 1 s; 0.4 by default, as before) by the api, so the render itself is unchanged.
- **Backdrop ("Video xuyên suốt", `RenderOptions.backdrop`):** the title scene's photo or clip runs under every
  scene (`render.with_backdrop`); the content scenes bring no picture. The scenes join by hard cuts (`concat`)
  whatever their transitions, and scene colours are not used. A clip used from past its first second is first cut
  there (`render.trim_backdrop`), so it loops back to the title scene's start; it is then read again for each scene
  from where the scene before left it (`render.backdrop_start`: the scene's start × its speed, wrapped into the
  clip's length) with `-stream_loop -1`, so the joins are seamless and a short clip loops; a photo's motion runs once over
  the whole video (`zoompan` counts from the scene's first frame over the video's frames). Each text box is looped
  for its scene's seconds and fades in and out over 0.3 s (the title's only out, as it is the cover; the last
  scene's only in). Photo layers ("Ảnh món") are laid on only in this mode. The backdrop is always silent: no scene's "Tiếng gốc" (`video_sound`) or clip words are
  used over it. Off, the filter graph is the one it
  always was.
- **Font:** Be Vietnam Pro Black (OFL) is bundled in the package, not installed per machine.

### Render Machines

With "Render và cảnh động chạy trên máy render" on (`app_settings.render_on_node`), the worker runs every light step
of a `render` or `motion` job, then packs what the render needs ([render_nodes.py](../api/src/reels_api/render_nodes.py)):
a zip of the job's files and a `manifest.json` (the render script, music, options, the fingerprint to save, or the
motion markup) in storage under `jobs/<id>/`, and sets `jobs.node_stage = "ready"` (migration 0052). The job stays
`running`, so the video stays locked; the worker's restart recovery and its exit check skip jobs with a `node_stage`.
A render machine (`render_nodes` row, token stored hashed) claims the oldest ready job (`taken`, `node_id`,
`node_seen_at`), downloads the bundle, renders it with `render_nodes.render_bundle` (the same `render_video`, and
`motion.render_clip`, and QC), uploads the MP4 and calls `done`; the api then saves it with `jobs.save_render` or
`motion.attach`, exactly as the worker does, and deletes the bundle. `fail` fails the job with the machine's reason.
A taken job silent for 10 minutes returns to `ready` on the next claim. A `ready` job can be cancelled from the video
page; nothing renders it on the VPS while the switch is on. Machine endpoints (`/api/node/...`) authenticate by
bearer token only and are exempt from the Origin check (main.py); member endpoints (`/api/render-nodes`) use the
login cookie.

### Media Library ("Kho tư liệu")

Photos and clips gathered once and used in any scene ([routes_media.py](../api/src/reels_api/routes_media.py)).

- **A dragged folder** is uploaded by the browser one file per request (`POST /api/media`, the file and its folder
  path), like every upload: a photo with the photo rules (jpg, png, webp, 15 MB), a clip with the clip rules (50 MB,
  MP4/MOV/WebM), a clip over a minute keeping its first minute. Folder paths are normalised (NFC, `/`, no empty or
  dot parts, 200 characters).
- **Pasted links** (`POST /api/media/links`, ten at a time) are downloaded with `remote_media.download`, the same
  rules as a link pasted on a scene: public addresses only, a TikTok video through yt-dlp, a photo or a video file
  otherwise. A link that fails is reported on its own and the others still come in. The link is kept as the item's
  source. The web's Google Ảnh (also "Ảnh không nền", `tbs=ic:trans`) and TikTok buttons only open a search for the
  product's name in the member's browser; the app never searches or downloads from Google by itself.
- **Using an item** (`POST /api/media/{id}/use`) copies it into the scene through the editor's own `_store_photo` and
  `_attach_clip`, with their locks and checks. Thumbnails are a photo, or a clip's frame at one second.
- **MCP:** `list_media`, `view_media` (the pictures of up to eight items, so the assistant chooses by looking),
  `add_media_from_links` and `set_scene_media_from_library`.

### Render QC

Every render job measures the MP4 it made before saving it ([qc.py](../api/src/reels_api/qc.py)) and stores the
result with it (`videos.qc`, migration 0049): `{"status": "pass" | "warn" | "fail", "checks": [...]}`, each check with
a Vietnamese label and its measure, the status being the worst check's. The thresholds follow the platforms'
delivery specs, as AIEV's QC does:

| Check | Pass | Warn | Fail |
| --- | --- | --- | --- |
| Format | 1080×1920 H.264, 30 fps | fps off by more than 0.5 | another size or codec; no audio track |
| Length | 20–40 s (the channel's) | outside 20–40 s | under 5 s |
| Loudness (EBU R128) | −14 LUFS ± 2 | ± 2–4 LU | beyond ± 4 LU; silent when narration or music is on (only a warning otherwise) |
| True peak | ≤ −1 dBTP | −1 to −0.5 | above −0.5 |
| Black frames (`blackdetect`, ≥ 0.25 s, not within 0.3 s of either end) | none | under 1 s | 1 s or more |
| Frozen picture (`freezedetect`, ≥ 2 s) | none | any | — |
| Dead air (`silencedetect` −45 dB, ≥ 1.5 s) and silence over the last 1.2 s | none | any | — |

QC never fails the render: a measure FFmpeg cannot make is a warning saying so. The video page shows it under the
MP4 ("Kiểm tra chất lượng"), and the MCP assistant reads it after each render (`docs/chatgpt.md`).

### Motion Scenes (HyperFrames)

A "Cảnh động" ([motion.py](../api/src/reels_api/motion.py)) is a scene whose clip is made from HTML + GSAP that an
assistant writes through the MCP tool `set_scene_motion`. The worker renders it with the HyperFrames CLI
(heygen-com/hyperframes, Apache-2.0, pinned in [api/Dockerfile.worker](../api/Dockerfile.worker) with GSAP and
its headless Chrome) into a 1080×1920, 30 fps MP4, which becomes the scene's clip like an upload. FFmpeg then makes
the video as before: HyperFrames never renders the whole video, and Remotion is not used.

- **The markup is a fragment** placed inside a 1080×1920 root of the scene's seconds (1–10, plus the crossfades and
  0.2 s so the clip never ends on a held frame). The page loads the image's GSAP from `assets/`, defines a paused
  timeline `tl` the markup adds its motion to, and the template's Be Vietnam Pro font. The scene's photo at the
  time of the request is copied (`motion.photo_key`) and served as `assets/photo.<ext>`, so a transparent product
  photo can move on screen; the clip then takes the photo's place on the scene.
- **It is untrusted.** Before it is stored, `check_markup` refuses document-level and embedding tags, external
  scripts, any URL scheme but `data:`, protocol-relative URLs, `@import`, network, storage, timer and `eval` APIs,
  and the clock and `Math.random` (a render must be the same every time), up to 100 000 characters. The worker's
  Chrome is started through a wrapper (`PRODUCER_HEADLESS_SHELL_PATH`) with `--proxy-server` pointing at a closed
  port, so only HyperFrames' own loopback file server answers; the render's environment sets the proxy variables
  the same way and turns off HyperFrames' update checks, telemetry and optional installs.
- **One job per video**, as always: the request stores the markup with `pending` and queues `motion` with the
  scene; the job renders (10 minutes at most, one Chrome worker, low-memory mode), checks the MP4 with the clip
  rules below, and makes it the scene's clip with the scene's seconds fixed to the motion's (`seconds_auto` off).
  A failed job leaves the scene's photo or clip as it was and keeps the markup for the assistant to fix.
- **The image build proves it works:** `python -m reels_api.motion` renders a short scene during the build, so a
  worker image whose Chrome cannot start never deploys. Tests use a fake `hyperframes` on PATH.

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
- **Split:** "Tách cảnh" in the preview calls `POST /scenes/{id}/split` with `at`, seconds into a content scene
  (1 s to `seconds` − 1 s; the title scene is refused). The scene keeps its text, voice text and narration and
  lasts `at` seconds; a new scene right after it (the later scenes move down one place) lasts the rest, with no
  text or voice text (so it is silent), the same keywords and image prompt, and its own copy of the photo or clip:
  a clip keeps its speed and starts `at` × speed later. Both parts have "Tự khớp lời đọc" off. Undoing it deletes
  the new scene and puts the first part's seconds back. The new scene keeps the colour and cuts in
  (`transition` "cut"), since the same picture goes on.
- **Effects:** `scenes.transition` (the transition into the scene; null: the video's `options.transition`) and
  `scenes.color` (a colour preset; null: as shot), migration 0037, both named presets of
  [effects.py](../worker/src/reels_render/effects.py) set by `PATCH /scenes/{id}` (null clears; the title scene
  refuses both). The job writes them into the scene's script entry only when set, and they join the render
  fingerprint only when set, so MP4s made before stay current. In the graph each boundary takes the scene's own
  `xfade` (a "cut" among transitions is a one-frame fade at the crossfade's offset, so the length and narration
  timing stay the timeline's; when every boundary is a cut the scenes are joined with `concat` as before), and a
  colour is one more filter step on the scene's picture before its text box is overlaid. The colour presets'
  filter chains are adapted from AIEV (MIT, notice in `effects.py`).
- **Layers:** `scene_layers` (migration 0038; one row per text, sticker or photo layer, deleted with its scene) holds
  `kind`, `text` or `sticker`, `start` (seconds into the scene), `seconds`, `x`/`y` (the centre), `size`,
  `style` and `animation`, all named presets of [layers.py](../worker/src/reels_render/layers.py), and `position`
  (laid on in that order). [routes_layers.py](../api/src/reels_api/routes_layers.py) under `/api/layers` adds
  (`POST`, with `scene_id`; refused on the title scene), changes (`PATCH /{id}`, any field but `kind`) and removes
  (`DELETE /{id}`) one layer under the video's lock, each returning the video like the scene endpoints, and draws
  `GET /{id}/image.png` (and `/stickers/{name}.png` for the picker) with the render core's own `render_layer`, so
  the studio's phone shows the exact picture. The scene payload lists its layers with that URL, versioned by
  what is drawn. The job writes them into the scene's script entry and they join the render fingerprint, both only
  when a scene has any. "Tách cảnh" moves the layers starting after the cut to the new scene, at the same moment.
  The render draws each picture once, loops it (`-loop 1 -t end`) so the entrance can fade its alpha in, and lays
  it on after the captions with `overlay` enabled between its start and its end (cut at the scene's end); a slide
  moves the overlay's x or y over the same 0.3 s.
- **Photo layers ("Ảnh món"):** `kind = "photo"` shows its scene's own photo (`scenes.image_key`, so every way of
  choosing a scene's photo chooses it), with `style` its frame (`rounded`, `circle`, `square`, or `plain` for a
  photo already cut out) and `size` its width (35, 48 or 65% of the frame), drawn by `layers.render_photo` with a
  6 px white edge and a soft shadow. Only a `single` video takes one, one per content scene, for the whole scene by
  default (`seconds` 60, stopped at the scene's end), left and right by turns. On a slide video it is kept, left out
  of the render and of the fingerprint. The render job copies the scene's photo into the script's layer as
  `image`; a photo layer whose scene has no photo blocks the render. A machine on older code refuses such a video:
  `backdrop` is sent to it only when on, as an option it does not know.
- **Sound:** `scene_sounds` (migration 0039; `sound`, `start` into the scene, `volume`, deleted with its scene),
  `scenes.music_level` and `videos.music_start`, all named presets or bounded numbers of
  [sounds.py](../worker/src/reels_render/sounds.py). [routes_sounds.py](../api/src/reels_api/routes_sounds.py)
  under `/api/sounds` adds, changes and removes one sound under the video's lock and serves
  `/library/{name}.mp3`, made once per api process by the render core's `make_sound`; `music_level` is set by
  `PATCH /scenes/{id}` and `music_start` by `PATCH /videos/{id}`. The job writes the sounds and the level into
  the scene's script entry when set and passes `music_start` to `render_video`; each joins the fingerprint only
  when set. "Tách cảnh" moves the sounds after the cut like the layers and copies the level. In the graph each
  sound is its own source filter (`aevalsrc`/`anoisesrc`), delayed to its second, padded to the video's length and
  added with amerge + pan after the narration; a scene's level is a `volume` expression on the music over its
  seconds, and the song's start an input seek (`-stream_loop -1 -ss`).
- **Notes:** `video_notes` (migration 0040; `at` seconds from the video's start, `text`, `status` open → sent →
  done, the AI's `reply`, who wrote it) and `knowledge_topics.revise_prompt`. [routes_notes.py](../api/src/reels_api/routes_notes.py)
  under `/api/notes` adds a note at a second within the video (any member, in any mode: a note changes nothing),
  changes or removes one that is not with the AI, and `POST /send/{video_id}` queues one `revise` job for every
  open note (refused while another job runs) and marks them sent. The job ([revise.py](../api/src/reels_api/revise.py))
  calls the team's LLM once (twice when the answer is unusable), applies what the rules allow and answers each
  note; a failed job opens its notes again. The video payload lists the notes with the scene playing at each.
- **Edit templates:** `edit_templates` (migration 0041; a name and the template as JSON) and the app setting
  `edit_template_default` ("app", a template id, or null). [routes_templates.py](../api/src/reels_api/routes_templates.py)
  under `/api/edit-templates` lists them (the app's own first, each with Vietnamese summary lines), saves one from
  a video, renames, removes (also clearing the default it was), sets the default, and `POST /apply` puts one on a
  video under its lock. `autoedit.apply_default` runs after the script or clone job writes the scenes and after
  "Tự viết". The studio's undo of an apply deletes the layers and sounds it added and patches each scene's
  transition, colour and music level back. `videos.ai_effects` (migration 0042) keeps "AI gợi ý hiệu ứng"; the
  script job then appends `autoedit.EFFECTS_FORMAT` to its prompt and `autoedit.apply_ai_effects` puts the
  answer's per-scene `effects` on after the default template, leaving out anything outside the presets.
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
  trim=end_frame=<clip frames>`.
  - It has no `zoompan` and no prescale.
  - At a speed other than 1× the first filter is `setpts=(PTS-STARTPTS)/<speed>`; at 1× the graph
    is unchanged.
  - `fps` comes right after it, so variable-frame-rate phone footage, and a clip at any speed,
    becomes constant 30 fps.
  - `tpad` holds the last frame when the clip ends early, and `trim` cuts the clip to the
    timeline's exact frame count, so crossfade offsets stay frame-exact.
  - No `setpts` follows `fps`: in FFmpeg 7.1 (the worker image) `setpts` marks the frame rate
    unknown (1/0), and `xfade` then refuses to join the clip to a 30 fps scene.
  - The clip's audio stream is referenced only when the scene has `"video_sound": true` ("Tiếng gốc",
    2026-11-07): `[<clip input>:a]atrim=start=<lead × speed>,asetpts=PTS-STARTPTS[,atempo=<speed>]`, padded or cut
    to the scene's exact samples and laid on the narration's track (added to the scene's narration when it has
    one), so the music ducks under it like under a voice and QC expects sound. `<lead>` is half a crossfade
    (0.2 s) for a content scene unless every boundary is a hard cut, because the clip's picture starts that much
    before its scene. A clip without a sound track renders silent with a warning. Otherwise the clip's sound is
    never used, and the graph is the one it always was.
  - A scene with `"words"` (`[{text, start, end}]` in the clip's own seconds) and its sound heard gets
    captions timed by those words (`captions.plan_word_captions`) instead of the narration's estimate: each word
    is placed at `scene start − lead + (word − video_start) / speed`, words outside the scene are left out.
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
| LLM (Claude and other providers) | Script generation, cloning and learning from a sample video, whose stills it is sent as JPEG images (Anthropic image blocks, OpenAI-style `image_url` data URIs) (built); drafting Knowledge Base content (planned) | Called only from the worker ([llm.py](../api/src/reels_api/llm.py)), with the provider the team chose on `/settings/ai`. Claude goes through the Anthropic SDK (default model `claude-sonnet-5-5`, with the server-side refusal fallback enabled); OpenAI, Gemini, DeepSeek, OpenRouter, Groq, xAI, Qwen, Ollama and a custom provider go through the OpenAI-compatible `POST {base URL}/chat/completions` with one user message and no `max_tokens`. An answer cut off by the model's length limit fails the job at once instead of being asked again. "Kiểm tra kết nối" calls `GET /models` (no tokens) from the api. Every call is logged with the provider, model and token counts. With nothing set on the page, Claude is used with `ANTHROPIC_API_KEY` / `CLAUDE_MODEL`. Knowledge drafting will use web search so it can return source URLs. |
| ElevenLabs | Scene narration in the render job | The premade "Adam" voice by default, model `eleven_v3` with `language_code: vi` (`eleven_multilingual_v2` does not speak Vietnamese). Voice and model are configurable; the key comes from Cài đặt › Nguồn tư liệu (encrypted, `source_keys.py`) or else `ELEVENLABS_API_KEY`. Paid per character, so each scene's MP3 is stored and reused. Speech-to-Text (`scribe_v2`, word timestamps, [stt.py](../api/src/reels_api/stt.py)) writes down a sample video's words once, in the `learn` job, with the same key; the language is detected. |
| VieNeu | Scene narration, for a video whose voice is a VieNeu one | Its OpenAI-compatible `POST /v1/audio/speech` (`model: vieneu-v4`, MP3 back in the response) at `https://api.vieneu.io/api`, bearer key from Cài đặt › Mô hình AI (encrypted, `source_keys.py`, name `vieneu`) or else `VIENEU_API_KEY`. The voices come from `GET /v1/voices?engine=v4` and are offered only once a key is set; the app stores them as `vieneu:<VieNeu voice id>` in `videos.options.voice_id`, which is how [tts.py](../api/src/reels_api/tts.py) picks the service. Same reuse of made MP3s and the same FFmpeg tempo as ElevenLabs. |
| Facebook Reels Publishing API | Posting a video to the team's one Page | Called only from the worker ([facebook.py](../api/src/reels_api/facebook.py)). Pages are connected on `/fanpages` by pasting a token, so there is no OAuth screen. A user or system user token is swapped for each Page's own token through `/me/accounts`, and that token is what is kept. Once the reel is live or scheduled, the publish job sets its cover to the first frame of the MP4 it holds (the title scene) with `POST /{video_id}/thumbnails` (`source`, `is_preferred=true`); a cover that cannot be made or is refused is only logged, and Facebook keeps the frame it picked. A post's numbers come from Video Insights, `GET /{video_id}/video_insights` (lifetime `fb_reels_total_plays` as views, `post_video_social_actions` for shares and comments, `post_video_likes_by_reaction_type` summed as reactions), which needs `read_insights` on the Page's token; `facebook.reel_insights` alone knows these names. All of them go in one call, which Meta fails whole with code 100 when it has retired any one of them (`post_impressions_unique`, June 2026). After a code 100 each metric is asked alone, a refused one comes back null and is logged, and only a reel whose every metric is refused reads as gone ("Facebook không còn reel này hoặc chưa có chỉ số"). A post's affiliate comment is written with `POST /{video_id}/comments` and edited with `POST /{comment_id}` (`pages_manage_engagement`); before a member's retry of an attempt whose answer was lost, `GET /{video_id}/comments` (`pages_read_user_content`) looks for one the Page already wrote. Visitors' comments are read with `GET /{video_id}/comments?filter=toplevel` (newest 100, each with its replies' authors, so an answer made on Facebook counts; Facebook answers code 100 both for a reel it no longer has and for one the token may not read, so `GET /{video_id}?fields=status` decides which the member is told); a reply is `POST /{comment_id}/comments` and a hide `POST /{comment_id}` with `is_hidden=true`. A Page's daily numbers are `GET /{page-id}/insights?period=day`, one metric per call so a retired one loses only its number: `page_media_view` (views), `page_total_media_view_unique` (reach), `page_post_engagements`; `facebook.PAGE_METRICS` alone knows the names. Each Page's token is checked by reading `GET /{page-id}?fields=name,followers_count` with it (`facebook.page_info`), which needs `pages_read_engagement`. |
| Stock photos (Pixabay, Pexels, Openverse) | The web editor's "Chọn từ kho ảnh" picker switches between three sources: Pexels (the default when it has a key), Pixabay (keys of Pixabay, Pexels and Gemini come from Cài đặt › Nguồn tư liệu, encrypted, or else `.env`, see `source_keys.py`), Pexels (vi-VN locale, portrait; offered only when it has a key) and Openverse (no key needed; optional registered OAuth credentials raise its rate limits; CC0 and public-domain-mark works only, filtered in the query and again per result). The picker opens each source in the language it indexes: the scene's English terms for Pixabay/Pexels, its Vietnamese terms for Openverse. "Tìm ảnh" takes the next result from one source, Pexels (the api's default `source`; the first source offered when Pexels is not) unless the member picks another from the arrow beside it (`POST /scenes/{id}/find-image?source=`), reading the keyword list in that source's language with the other list as fallback; the CLI's stock search stays Pixabay-only. A chosen photo from any source is re-checked against that source's results (searched with the same orientation), downloaded by the api and stored with the scene, like an upload; the grid's thumbnails are only shown. Filters (`orientation` = vertical by default, square or all; `hide_used`): each source is asked for the shape where it can (Pixabay `orientation=vertical`, Pexels `portrait`/`square`, Openverse `aspect_ratio=tall`/`square`) and results whose size is known are checked again by shape and dropped when the served file's short side is under 640 px; photos another scene of the video shows (by `image_source`) are hidden, and "Tìm ảnh" never picks one. Pixabay's search cache is kept per keyword and orientation. A Cloudflare bot-check page in front of Pixabay (HTML instead of the API's text) is reported as the network being blocked, not as a rate limit. After a script or clone job, a `photos` job ("Tự tìm ảnh", [auto_photos.py](../api/src/reels_api/auto_photos.py), on unless the team turned it off on Cài đặt › Nguồn tư liệu) gives every scene without a photo or clip one stock photo with the same rules (tall, big enough, never one another scene shows; Pexels, Pixabay, Openverse in that order, skipping sources turned off, without a key or failing in that job), stored with `scenes.image_auto` until a member changes or keeps it; it never makes AI photos and fails only when every source failed |
| Photos and clips from any site (pasted link or dragged photo), TikTok videos | "Dán ảnh/link", a drop from another tab, "Tìm trên Google" and "Tìm trên TikTok" (only open Google Ảnh or TikTok's video search in a tab) | `POST /scenes/{id}/media-from-url` ([remote_media.py](../api/src/reels_api/remote_media.py)) downloads the link inside the request: http(s) only, the host must resolve to public internet addresses and every connection, redirects included, is checked against the address it reached; at most 50 MB and 60 s. What arrived decides: an MP4/MOV/WebM container is a clip (then `clips.first_part` keeps its first minute and the clip upload's checks run), anything else must pass the photo upload's checks within 15 MB. A `tiktok.com` link (any subdomain) goes to yt-dlp instead, which fetches the single video's file from TikTok (largest size, H.264 before HEVC, 50 MB), refusing photo posts and lists. A photo's link is stored as `image_source`; a clip's is not kept. A copied photo or a `data:` thumbnail is uploaded by the browser through the normal photo upload. The member chooses the photo or clip and is responsible for it, as for an upload; no Google or TikTok API is used. |
| Photos and clips the topic group already uses | "Đã dùng trong nhóm" on a scene | `GET /scenes/{id}/group-media?q=` lists, from the other videos of the scene's topic group, the scenes holding a photo or clip (at most 60): with `q`, those whose keywords and text hold every typed word, accents and case ignored; without, all, ranked by the words their keywords and text share with this scene's keywords, newest first among equals. `POST /scenes/{id}/reuse` copies one into the scene as its own file (a photo keeps its `image_source`, a clip goes through the clip upload's checks); both videos stay independent. Another group's scene is refused. |
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
| `videos` | Topic, whether the script exists, how it is built (`mode`, migration 0054: `slides`, each scene over its own photo or clip, or `single`, "Video xuyên suốt", the title scene's photo or clip under every scene; switching keeps every photo, clip and layer), narration on/off, its own settings (`options`: voice, reading speed as a tempo factor, voice level, ducking, the pause after narration, transition, motion, zoom, text style, captions; empty for older videos, which render the original template, see [video_options.py](../api/src/reels_api/video_options.py)), title options, caption, hashtags, affiliate suggestions, pinned comment, self-review notes, music suggestions, optional MP3 with volume, the current MP4 with its length, render time and render fingerprint, whether a member wrote the script by hand (`hand_written`), whether a member's own Claude wrote it through MCP (`written_via`, migration 0056: `assistant`, see [chatgpt.md](chatgpt.md)), thumbnail, the clone snapshot for a cloned draft, the sample video it learned from and the way chosen (`reference_id`, `reference_mode`: quick, twostep, review, reuse), creator. |
| `video_references` | A sample video members learn from ("Từ video mẫu", [reference.py](../api/src/reels_api/reference.py)): the pasted link (null for an upload), a display name (the link or file name), the stored file `references/<id>/source-….<ext>` (null until the job downloads a link), its length, its words with their seconds (ElevenLabs Speech-to-Text; empty when silent; as timed lines in `transcript` and, since migration 0055, word by word in `words` `[{text, start, end}]`), its stills `[{second, key, note}]` (up to 16, the note written by the analysis), the analysis (empty until written; members may edit it), who added it and when. Kept until a member deletes it, so more videos can learn from it and cut clips from it; deleting it removes its files, and the videos made from it keep their scripts and clips (`videos.reference_id` becomes null). |
| `knowledge_topics` | One topic group of `/knowledge`: unique name, script prompt, clone prompt, "Từ video mẫu" learn and analyse prompts (`learn_prompt`, `analyze_prompt`; empty: the defaults in `prompts/`), banned words, `photo_hint` ("Gợi ý tìm ảnh", added to both prompts for the photo keywords; empty: nothing added); its 30-day plan's prompt (empty: the default), start date (day 1, Vietnam time), ideas per day for the AI (3–5), its posting times (`plan_post_times`, 1–5 "HH:MM", the n-th idea of a day suggested at the n-th), the AI's last plan as a draft (`plan_draft`) until a member saves or drops it, and `video_target`, the number of videos its trial counts towards ("Tiến độ verdict", null: no banner). Empty until written. A video points to one; it cannot be deleted while videos do. Replaced the `settings` rows, which stay unread so a rollback finds them. |
| `topic_plan_items` | One idea of a topic group's 30-day plan ([plans.py](../api/src/reels_api/plans.py), [routes_plans.py](../api/src/reels_api/routes_plans.py)): day (1–30, or null: the group's Backlog), place in the day (or the Backlog), topic, pain group, pain, hook, the video made from it (unique; `SET NULL` when the video is deleted), who changed it. At most 5 a day (300 in the Backlog) and no topic twice, checked by the api under a lock on the topic group. Its status is read from the video and its posts (Đã lên lịch, Đã đăng). Deleted with the group. Saving an imported or AI plan replaces the 30 days and keeps the Backlog, but for an idea the new plan puts on a day; an idea with the topic of one that had a video keeps that video. |
| `scenes` | Belongs to a video; the title scene or a content scene, order, seconds (and `seconds_auto`, "Tự khớp lời đọc": once the narration is made the seconds become its length plus the pauses around it, within 1–10 s; typing the seconds turns it off; on for the scenes the app writes, off for scenes from before 0034), on-screen text with `*red*` markup, voice text, Vietnamese and English stock-search keywords, image prompt, the stored photo and where it came from (upload, `ai:<model>` for a generated one, or the stock photo's URL), the reason a photo is missing, the optional clip with its length and start time (and, migration 0055, `video_sound`, "Tiếng gốc": the clip's own sound is heard in the render, and `words`, what that sound says `[{text, start, end}]` in the clip's own seconds, set by "Edit từ footage"; a new or removed clip clears both, a split copies them), the last narration MP3 with its length and the signature it was made from, and where a member dragged its text box (`text_x`, `text_y`, the box centre; null: the video's place in `videos.options.text_position`, else the template's). Whether its photo is the app's unchecked pick (`image_auto`). `motion` (JSONB, migration 0048): a "Cảnh động" — the HTML an assistant wrote, its seconds, a copy of the photo it may show (`photo_key`), the clip it made (`clip_key`) and `pending` while its job runs; shown only while `video_key` is still that clip. |
| `fanpages` | A connected Facebook Page: its id and name, the Page's encrypted token and its last characters, in use or stopped, who changed it last, and the worker's last check of its token: when, its error (null when it worked), when a member asked for one, the followers it read, and what went wrong reading its Page Insights (`insights_error`); the one topic group it posts (`knowledge_topic_id`, `SET NULL` when the group is deleted) and its own posting times (`post_times`, "HH:MM" in Vietnam; null: the group's). |
| `articles` | An article ("Bài viết", [articles.py](../api/src/reels_api/articles.py), [routes_articles.py](../api/src/reels_api/routes_articles.py)): a photo or text post for a Page, named "article" in code because "post" already means a `publications` row. Its topic group (`SET NULL` when the group goes), kind (`kien_thuc`, `meo`, `cau_hoi`, `canh_bao`, `tra_loi_binh_luan`, `checklist`), topic, caption, up to 5 hashtags, an optional picture (`image_key`, `image_kind`: `text_card` drawn by the api, `link` with the pasted link kept in `image_source`, or `ai`, not offered yet), the visitor's comment a `tra_loi_binh_luan` article answers, who made it and when. No picture is a text post. Its status is read from its `publications`: a draft, being posted, failed, scheduled, published. Like a video, it has a pinned comment (what its posts' comment opens with, before the products' links) and product ideas with their Shopee search (`affiliates`, `suggest_requested_at`, `suggest_by_id`, `suggested_at`, `suggest_error`). |
| `page_queue_items` | A rendered video waiting in a Page's posting queue ([page_queue.py](../api/src/reels_api/page_queue.py), [routes_queue.py](../api/src/reels_api/routes_queue.py)): the Page, the video (unique: one queue at a time; deleted with the video or the Page), its place, whether its post writes the affiliate comment, who added it and when, and when the worker last tried it and why it could not schedule it then (`tried_at`, `error`). The row is deleted once its post is made. |
| `fanpage_followers` | A Page's followers on one day in Vietnam time, the last number read that day; one row per Page and day. |
| `fanpage_insights` | A Page's views, reach and engagements for one day from Page Insights (Facebook's day), each null when not given; the last 7 days are rewritten at each check. |
| `page_comments` | A visitor's top-level comment under a reel the app posted: Facebook's id, author name, text, time, whether the Page answered it (on Facebook or through the app) or it is hidden, "Bỏ qua", and the reply or hide a member asked for, with when it was sent, Facebook's id of the reply, the error and who handled it. |
| `publications` | One post of a video's MP4 to a platform, whatever platform the video was made for (`facebook`, `youtube` or `instagram` for a post made by hand there and recorded with its link, `post_url`, through [routes_manual_posts.py](../api/src/reels_api/routes_manual_posts.py), or `tiktok` for a post made by hand in TikTok's app and recorded with its link, `post_url`, and the member's TikTok account, `affiliate_account_id`, or one sent through TikTok's Content Posting API: `publish_mode` `draft` or `direct`, a direct post's `privacy_level`, TikTok's `publish_id` as `remote_id` and the link added afterwards by its sender; the Facebook readings keep to `platform = 'facebook'`, so none touches a TikTok post); a video posted again has one row per post, at most one of them pending: the Fanpage, pending, scheduled, published, cancelled (never public) or deleted (taken off the platform after going public), the scheduled time, the platform's id of the post and the MP4 sent, who started it, who cancelled or deleted it and when (nobody when a check found it so on Facebook), when Facebook was last checked (`checked_at`), and when its numbers were last read (`metrics_tried_at`), what went wrong then (`metrics_error`) and when a member pressed "Cập nhật view" (`metrics_requested_at`); whether the worker writes the affiliate comment by itself (`auto_comment`, false for posts made before it), the comment's Facebook id and text, when it was last tried (`comment_sent_at`) and written (`commented_at`), what went wrong (`comment_error`), and when a member pressed "Bình luận ngay" (`comment_requested_at`); when its visitors' comments were last read (`comments_read_at`) and what went wrong then (`comments_error`); where each scene starts and ends in the MP4 it sent (`scene_marks`, `{label, start, end}` in seconds, taken by the publish job when it uploads; null for posts made before). A post of an article ("Bài viết") has `article_id` instead of `video_id` (exactly one is set) and keeps the text it sent (`post_text`), so a retry after a lost answer finds that post on the Page; one pending post per article and platform. Code that reads every post's video keeps to `video_id IS NOT NULL` ("Bài đăng", a Page's dashboard, the reels' medians). |
| `post_metrics` | A post's views, shares, comments and reactions on Facebook, its plays without replays, replays, reach, average and total watch time (ms), follows it brought, and its retention curve (`retention`, the share of plays still watching at evenly spaced points, from 1), each null when Facebook does not give it, with when they were read: one `latest` row, rewritten by every reading, and at most one `48h` row, never rewritten. An article's post has no views: its `reach` (Post Insights' `post_total_media_view_unique`), shares, comments and reactions are kept, the rest null. |
| `jobs` | Belongs to a video; kind (script, clone, learn: a script from a sample video, render, publish, unpublish: takes the post `publication_id` off Facebook; check: reads that post on Facebook and records what it says; image, photos: the "Tự tìm ảnh" queued after a script or clone; voice: "Tạo giọng thật" in the preview, the narration a render would make and nothing else; an image job may name one scene, `scene_id`, and its provider, `image_provider`), status (queued, running, done, failed, cancelled), who started it, timings, Vietnamese error plus technical detail, number of LLM calls (`claude_calls`, named for the first provider) and of Gemini image calls, the provider and model a script or clone job wrote with, the job it retries. At most one queued or running job per video. |
| `jobs` | Belongs to a video, except a `plan` job ("Tạo bằng AI" on `/knowledge`), which belongs to a topic group (`knowledge_topic_id`, one queued or running per group) and writes the group's plan draft, and an article's jobs, which belong to the article (`article_id`, one queued or running per article): `article_caption` ("AI viết", replaces its caption and hashtags), and `publish`, `unpublish` and `check` for its posts, as for a video's; kind (script, clone, learn: a script from a sample video, render, publish, unpublish: takes the post `publication_id` off Facebook; check: reads that post on Facebook and records what it says; image, photos: the "Tự tìm ảnh" queued after a script or clone; voice: "Tạo giọng thật" in the preview, the narration a render would make and nothing else; motion: renders one scene's "Cảnh động" into its clip, [motion.py](../api/src/reels_api/motion.py); tiktok_publish: sends the TikTok post `publication_id` through TikTok's Content Posting API with its sender's connection, [tiktok_publish.py](../api/src/reels_api/tiktok_publish.py); an image or motion job names one scene, `scene_id`, and its provider, `image_provider`), status (queued, running, done, failed, cancelled), who started it, timings, Vietnamese error plus technical detail, number of LLM calls (`claude_calls`, named for the first provider) and of Gemini image calls, the provider and model a script or clone job wrote with, the job it retries. At most one queued or running job per video. |
| `settings` | The prompts and banned words before `knowledge_topics`; no longer read. |
| `llm_providers` | One row per provider set up on `/settings/ai` (the list itself is fixed in [llm.py](../api/src/reels_api/llm.py)): base URL and model (empty means the provider's default), the API key encrypted like a Fanpage token ([crypto.py](../api/src/reels_api/crypto.py)) and its last characters, who changed it last. |
| `app_settings` | Team-wide settings from the Cài đặt pages by key: `llm_provider` (the provider that writes scripts; Claude when unset), `video_defaults` (what a new video's settings, narration switch, music level and music start as; the music is `music_track_id`, a library track copied into each new video when it is created, skipped when the track is gone), `stock_sources_off` (stock sources the team turned off). |
| `media_items` | The team's "Kho tư liệu" ([routes_media.py](../api/src/reels_api/routes_media.py), migration 0050): `kind` photo or clip, the stored file, its name, the `folder` it was dragged in with or typed ("Nồi chiên 5L/cảnh quay"), the link it was downloaded from (`source_url`), a clip's seconds, who added it and when. Using one in a scene copies the file into the video, like "Đã dùng trong nhóm", so deleting it never changes a video. |
| `music_tracks` | The team music library: name, topics (names of Kho kiến thức groups or "chung", [music_topics.py](../api/src/reels_api/music_topics.py): renaming a group renames it on the tracks, deleting one takes it off them, a track left with none becomes "chung"; tags from the old fixed list stay until edited off) and one mood (a fixed list in [routes_music.py](../api/src/reels_api/routes_music.py)), source/license note, the stored MP3, who added it. Choosing a track for a video copies the file into the video's folder, so editing or deleting the track never changes a video or its render. |
| `affiliate_products` | The team's products, typed in from the affiliate dashboard or found through Shopee's API: platform (`shopee` or `tiktok_shop`), topic group, name, the link a member pasted (none for API products: each Page gets its own), the product page and image, Shopee's item id, shop, shop type, rating, sales, price, commission rate and when it ends, draft or approved, who approved it and when, creator, when the daily check last read it, and whether the worker is to read it from Shopee
(`lookup_requested_at`, `lookup_by_id`) or could not (`lookup_error`). Approval follows the platform's rules in [affiliate.py](../api/src/reels_api/affiliate.py) (Shopee: any shop type since 2026-11-05, at least 4.7 stars, 100 sales, no banned word, a commission not expired); changing an approved row sends it back to draft. A topic group with products cannot be deleted. |
| `tiktok_connections` | A member's TikTok account connected through TikTok's Login Kit ([tiktok_connections.py](../api/src/reels_api/tiktok_connections.py)): owner, the TikTok `AffiliateAccount` (one connection each), TikTok's `open_id` (one member each), username, display name, avatar, both tokens encrypted like a Fanpage token and their ends, the scopes granted, and `last_error` when a refresh was refused (the member connects again). TikTok replaces the refresh token on every refresh, so both tokens are saved over the old ones each time; a token ending within 5 minutes is refreshed before use. No token, nor any part of one, leaves the server. `tiktok_oauth_states` keeps the hash of each "Kết nối TikTok" state, its member and its 10-minute end, used once. |
| `affiliate_accounts` | A member's own account: platform (`shopee` with the Open API's App ID and Secret, encrypted with its last characters kept, or `tiktok` with the profile link), name, owner, in use, when the worker last read its orders and what went wrong. Only its owner reads or changes it ([routes_affiliate_accounts.py](../api/src/reels_api/routes_affiliate_accounts.py)); one with posts or orders is only stopped. |
| `affiliate_links` | A Shopee short link made with a Page's account for one product, video and Page (sub ids `v<video>`, `p<page>`); made once, when the comment is first written, and reused. An article's link has `article_id` instead of `video_id` (sub ids `bv<article>`, `p<page>`), one partial unique index for each. |
| `affiliate_suggestions` | Shopee's products for one of a video's product ideas, best first; replaced by each search, except the rows a member pasted on the video (keyword "Link đã dán", `affiliate_rounds.PASTED`). An article's suggestions have `article_id` instead of `video_id` (exactly one is set). |
| `affiliate_conversions` | One item of an order Shopee credited to an account: Shopee's order and item, the video and Page its sub ids named, when, the item, the commission (VND) and Shopee's status; rewritten by each reading. |
| `video_presence` | Who has a video open: one row per open video page (`tab`, a random id the page picks), the member, whether that page is in "Chỉnh sửa", and when it last reported. Rows silent for 30 s are deleted at the next report ([routes_presence.py](../api/src/reels_api/routes_presence.py)); deleted with the video or the user. |
| `article_affiliate_products` | At most two approved Shopee products attached to an article; their links go in the comment the worker writes under its post, never in its caption. |
| `video_affiliate_products` | The products attached to a video, of its platform's kind; deleted with either side. Only an approved product that meets the rules can be added; one that later stops qualifying stays, flagged, and is left out of the copied comment. |

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
  - **The Page queues** (the "Lịch đăng" tab of a Page's dashboard on "Quản lý Page", and "Thêm vào hàng chờ" on the video). Once a minute, beside the post checks, the worker's `page_queue.fill` gives
    each Page in use whose last token check worked, and whose queue is not empty, at most one post: the first
    video of its queue that can go is given the Page's next free posting time (its own `post_times`, else its
    group's) between 30 minutes and 48 hours ahead. A time is free when no open post of the Page is within 30
    minutes of it, so a post scheduled by hand takes its time too. The worker then makes the `publications` row
    (pending, scheduled at that time, made by the member who queued it) and a `publish` job, exactly what "Đăng"
    with "Hẹn giờ" makes, and deletes the queue row. A video that cannot go (no or an outdated MP4, the Page
    already holds this MP4, a job or a post on its way) stays in the queue with the reason (`error`) and the next
    one goes instead. Only 48 hours are filled because Facebook keeps the MP4 sent with a scheduled reel. Nothing
    in the request calls Facebook: `POST /api/queue` (`{video_id, fanpage_id?, auto_comment}`; without a Page,
    the member's own Page in use of the video's topic group, the shorter queue of two), `DELETE
    /api/queue/items/{id}` (the member who added it or the Page's owner), `POST /api/queue/pages/{id}/order` and
    `PATCH /api/queue/pages/{id}` (`knowledge_topic_id`, `post_times`; the Page's owner only), `GET /api/queue`
    (every Page in use with its free times and queue) and `GET /api/queue/videos/{id}`.
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
    gone: a 404, or the 400 (#100) Facebook really answers, which it also gives a token that lost the
    Page, so that answer counts only while the same token still reads the Page (`facebook._gone`). The
    "Kiểm tra" and "Thử lại" reads follow the same rule. A status read or delete that fails fails the job
    and leaves the post as it was.
  - **Never a second post by accident.** The reel's id and its MP4 are saved before the upload, and the moment
    Facebook is asked to publish is saved before asking. A retry reads the reel's status first,
    because an attempt may have reached Facebook whatever it reported. A live reel needs nothing,
    and the app records what Facebook says. One Facebook was asked to publish and is still
    processing is waited for. A reel holding the current MP4 is finished again; whether a second
    finish is harmless is assumed, because the docs do not say. A new reel is made only when the old
    one is gone (as above), refused, or not fully received, or when it holds an older render and
    was never asked to publish, or was asked over 30 minutes ago. A status read that fails or says
    nothing fails the job and posts nothing.
  - The job repeats the MP4 and time checks, because "Thử lại" skips the endpoint.
  - The job locks the video like a render, for the minute or so it takes.
  - `GET /api/posts` ([routes_posts.py](../api/src/reels_api/routes_posts.py)) reads
    every Facebook post for `/posts` (list and calendar), with the video's `thumbnail_url`, `busy`
    while the video has an active job, and `attempt` for a pending post: `working` until its
    video's last publish job fails, then `failed` with that job's `job_id` (what "Thử lại" sends to
    `POST /api/jobs/{id}/retry`) and `error`; null for any other post. The calendar loads every row, keeps the
    scheduled and published ones and groups them in the browser, which is enough at 1–3 videos a day.
  - **A post's numbers** ([metrics.py](../api/src/reels_api/metrics.py)) are read by the worker
    between jobs, not by a job: a reading writes only numbers, so it never locks the video and is
    not listed under Jobs. Every 5 seconds the worker reads up to 3 due posts, asked ones first, then
    the longest unread. A public post is due an hour after it went live, then once a day for 14
    days; the first reading at least 48 hours after it went live, if within 72 hours, is also kept
    as its `48h` row. A failed reading records Facebook's reason on the post and waits a day, never
    looping. "Cập nhật view", `POST /api/posts/{id}/metrics`, only sets `metrics_requested_at` for a
    public post (409 otherwise), so a request never calls Facebook; the worker reads it within
    seconds, even past the 14 days. Opening "Bài đăng" calls `POST /api/posts/freshen`, which asks the same
    for every post still followed whose last reading is over 15 minutes old and not asked yet (`{"asked": n}`). Every post payload has `metrics`: `latest` and `at_48h` (each
    null until read), `error`, `pending` while an asked reading has not run, `analysis`, and
    `length_seconds` with `scenes` (the post's `scene_marks`; null and empty for older posts).
  - **Watch time and retention.** The same Video Insights call also asks for
    `blue_reels_play_count`, `fb_reels_replay_count`, `post_impressions_unique`,
    `post_video_avg_time_watched`, `post_video_view_time`, `post_video_followers` and
    `post_video_retention_graph`, so they cost nothing more to read. The curve is kept as fractions in
    segment order (values above 1.5 are read as percent). A reading's payload adds
    `avg_watch_seconds`, `view_time_seconds`, `watch_ratio` (the average over the posted length, the
    last scene mark's end; it can pass 1 because replays count) and `retention`. "Phân tích" spreads
    the curve's points evenly over the reel's length and lays the scene marks over it. The names and
    shapes come from Meta's docs and are tested only against the fake service; `facebook.reel_insights`
    is the one place to change if a real Page answers differently.
  - **The affiliate comment** ([post_comments.py](../api/src/reels_api/post_comments.py)) is written by the
    worker the same way, between jobs: up to 3 due posts every 5 seconds, asked ones first. Its text is the
    video's pinned comment, then "name: link" for each attached product that is approved and still meets the
    rules (`affiliate.comment_text`); a Shopee product's link is the Page's own when its owner set a Shopee
    account (made once with `generateShortLink` and kept in `affiliate_links`), else the link a member
    pasted, and a Shopee failure is recorded like a Facebook one. A post is due when it was made with "Tự bình luận" (`auto_comment`, the
    default in "Đăng"), has been live 2 minutes and has had no attempt, or when a member asked with "Bình luận
    ngay" / "Cập nhật bình luận", `POST /api/posts/{id}/comment` (409 unless live). The attempt is stamped
    before Facebook is asked; a comment already written is edited, never written again, and a retry after a
    lost answer first looks for the Page's comment with the same text. A failed attempt (or no text to write)
    is recorded and waits for a member. Products are attached on the video page before posting, or on
    `/affiliate` after, with `PUT /api/affiliate-products/videos/{id}`; changing them asks the worker to edit
    each live post's comment. Every post payload has `comment` (`state`: off, waiting, pending, done or failed;
    `auto`, `error`, `text`, `at`). Members still pin the comment on Facebook.
  - **Shopee** ([affiliate_rounds.py](../api/src/reels_api/affiliate_rounds.py), [shopee.py](../api/src/reels_api/shopee.py))
    is the worker's too, between jobs: the suggestions of one asked video per round (a new script asks by itself
    when its writer has a Shopee account; "Tìm sản phẩm" is `POST /api/affiliate-products/videos/{id}/suggestions`,
    shown by `GET` there, "Chọn" is `POST .../choose`), searched with the asking member's account. A video's and an
    article's payload carry `suggest` (`state`, `error`, `at`: when the last search finished); the page reloads the
    suggestions when `state` or `at` changes, since a search can finish before the page ever sees it pending. Up to 10
    products added by a pasted link (`POST /api/affiliate-products/links`, or on the video
    `POST /api/affiliate-products/videos/{id}/links`, which also works without an App ID and then leaves a draft
    holding only the link) or imported from Shopee Affiliate's
    file (`POST /api/affiliate-products/import`, read in the request, no Shopee call) that wait to be read
    (`lookup_requested_at`): the item id comes from the link, a short link (s.shopee.vn) only asked for its
    redirect, then `productOfferV2` fills name, shop, stars, sales, price and commission, with the member's own
    account or else any member's; a failure is kept in `lookup_error` until "Lấy lại thông tin"
    (`POST .../{id}/lookup`) or an edit by hand; up to 5 approved API products whose last check is a day old; and up to 2 accounts whose orders were last read a day
    ago (the last 30 days, kept by order and item). Each failure is recorded where members see it and waits.
  - **"Bình luận"** ([comments_inbox.py](../api/src/reels_api/comments_inbox.py),
    [routes_comments.py](../api/src/reels_api/routes_comments.py)) is the worker's too, between jobs:
    each round sends up to 3 replies or hides members asked for, then reads the comments of up to 3
    live posts of the last 14 days due a reading (every 30 minutes, or at once after "Tải bình luận
    mới", `POST /api/comments/refresh`). The Page's own comments are left out. `GET /api/comments`
    lists the newest 300 (`state=open`: not answered, hidden or set aside, or whose last send failed),
    with the reel, its Page and the Pages whose reading failed. `POST /api/comments/{id}/reply`
    (1–2000 characters, 409 once replied through the app), `/hide` and `/dismiss` only record what the
    member asked; a reply or hide is stamped before Facebook is asked and never resent by itself,
    and a retried reply first looks for the Page's reply with the same text. Replies are written by
    members; the app writes no words of its own here.
  - **Each Page's check** ([fanpages.py](../api/src/reels_api/fanpages.py)) is done by the worker the
    same way, between jobs and not as a job: every 5 seconds it checks up to 3 due Pages in use,
    asked ones first. A Page is due when never checked (just connected, or given a new token, which
    clears the last result), 12 hours after its last check, or when asked. A check reads the Page
    with its own token and records the error in Vietnamese, or keeps the Page's current name and its
    followers (on the Page and as that day's `fanpage_followers` row); it never changes
    `updated_at`, which is a member's change. A failed check waits like any other, never looping.
    "Kiểm tra ngay", `POST /api/fanpages/{id}/check`, only sets `check_requested_at` (422 for a
    stopped Page); opening "Quản lý Page" calls `POST /api/fanpages/freshen`, which asks it for every Page in use
    checked over 15 minutes ago and not asked yet, and opening "Bình luận" calls `POST /api/comments/freshen`, which
    makes every followed reel read over 15 minutes ago due. `GET /api/fanpages` gives each Page `check` (`checked_at`, `error`, `pending`,
    `followers`, and `followers_this_week`, counted from the last number before this week's Monday,
    null until there is one) and `scheduled_posts`, its posts still waiting for their time, which a
    broken token leaves without "Kiểm tra" or "Hủy đăng". The video payload's `fanpages` carry each
    Page's last `error`, so "Đăng" warns before posting to a broken one, and its `owner`, the name of
    the member who connected (or last turned on) the Page. A check whose token works
    also reads the Page's last 7 days of Page Insights into `fanpage_insights`; a refusal (no
    `read_insights`, a retired metric) is kept as `insights_error`, never as a broken connection.
    The list gives each Page `insights` (`last_7_days` sums and `error`), and
    `GET /api/fanpages/{id}/insights` its last 30 days with the followers of each day.
    `GET /api/fanpages/{id}/dashboard?days=7|28|90` ([page_dashboard.py](../api/src/reels_api/page_dashboard.py))
    is one Page's dashboard, worked out on each request and never stored: the period is the last `days` days in
    Vietnam time, today included, and each figure (`value`, `previous`, `change` as a fraction, null with nothing
    to compare) is set against the same number of days before it. `series` has every day of the period with its
    Page Insights numbers, its followers reading and the app's posts that went live that day; `totals` sums views,
    reach and engagements, counts the posts and gives `followers_gain` (the last reading in the period less the
    last one before it); `post_numbers` sums reactions, comments and shares and weights the average watch time by
    views over the latest readings of the period's posts (close to, not exactly, what the Page earned then);
    `latest_post` is the newest live post with its latest reading; `upcoming` the posts waiting for their time in
    the next 7 days and the Page's free posting times then (`page_queue.free_slots`). Other `days` are a 422.
    `GET /api/fanpages/{id}/content?days=7|28|90` (`page_dashboard.content`) is the dashboard's "Nội dung" tab,
    also worked out on each request: every Facebook post the app made to the Page that went live in the period
    (Vietnam time), newest first, a reel taken down after going live included as `deleted`. Each row has the
    video, `live_at`, `closed_at`, the reel's `url` (null once taken down), its `latest` reading (`numbers`: views,
    reach, reactions, comments, shares, average watch time, follows, `measured_at`; null until read), `views_48h`
    and `times_median` against the Page's median (analytics.py), `can_refresh` (a reel on Facebook, for "Cập nhật
    view", which stays `POST /api/posts/{id}/metrics`), `pending` and the last reading `error`; `median` gives the
    Page's median, sample count and the samples it needs. Sorting, the chosen columns and the CSV file are the
    web's, from these rows.
    `DELETE /api/fanpages/{id}` removes a stopped Page with no post at all (409 otherwise), its
    followers and numbers going with it; each listed Page carries `posts`, its count of posts.
  - **What the numbers mean** ([analytics.py](../api/src/reels_api/analytics.py)) is worked out from
    the `48h` rows when asked, never stored. Each Page's median views is taken over its posts that
    went live in the last 60 days; a post is compared with it (its multiple of the median) once the
    Page has at least 5 measured posts. A cancelled or deleted post counts in no median and no weekly
    KPI; its own `48h` and `latest` rows stay, as history. `analysis` gives the Page's median and sample count, the
    post's multiple of it and its share/view at 48 hours. There is no "Video thắng" flag (dropped
    2026-11-03, see decisions). `GET /api/videos` gives each video its topic group, its plan day and
    `post`: its live or scheduled Facebook posts in one line (`state` posted or scheduled, the Page and
    time of the post with the most views or the next one set, how many Pages, the `latest` views of
    every live post added up, and that post's 48-hour shares, share/view, `share_met` and multiple of
    the median). The posts, their readings and the medians are read once for the whole list.
    `GET /api/posts/kpis` gives this week and last, Monday to Sunday in Vietnam time (a fixed UTC+7,
    which has no daylight saving): posts measured, median views, and how many reached
    share/view ≥ 0.2 % of those with both numbers.
    null until read), `error`, and `pending` while an asked reading has not run.
- **30-day plan:** `/api/plans/{group}` reads and changes a group's plan (start date, ideas per
  day, posting times, video target, prompt; ideas added, edited, moved and deleted under
  `/api/plans/items/{id}`, a null `day` being the Backlog; `PUT .../items` replaces the 30 days and
  keeps the Backlog; `POST .../backlog` adds a previewed file's ideas to the Backlog, skipping topics
  already there). `POST .../import` only reads a file and answers the preview (a file without days
  can only go to the Backlog); `POST .../generate` queues the plan job, whose result waits in
  `plan_draft`. Each idea carries `suggested_post_at` (its day at the posting time of its place,
  until that time is past) and `post_at` from its post; `GET /api/plans/{group}` also gives each
  idea's Facebook posts that went live with their 48-hour numbers only (never `latest`), compared
  with `analytics.medians`, read once for the whole plan, and `analytics.SHARE_GOAL`.
  `GET /api/plans/today` gives every group whose plan has a today its ideas of today, the last day
  from today on that has a video for every idea, and all its topics. A video's `plan_idea` carries
  `suggested_post_at`, which "Đăng" starts with. `POST /api/videos`
  takes an optional `plan_item_id`, refused when the idea already has a video or belongs to another
  group; the script job then passes the idea's pain and hook to the prompt
  ([content.md](content.md#script-generation-contract)). The job log names a plan job "Kế hoạch 30
  ngày · <nhóm>".
- **"Tự viết" (hand-written video):** `POST /api/videos` with `mode: "manual"` queues no job and
  makes no LLM call. The group is still required (banned words, team defaults, the plan), but not
  its script prompt. The video is saved with its script at once (`has_script`, `hand_written`):
  the title scene's text is the topic (also the only title option, 3 s), and `script` (at most 5000
  characters) gives one content scene per paragraph, split at blank lines. In a paragraph, lines
  starting with "Đọc:" are its voice text and the other lines its on-screen text, with the line
  breaks kept. Each scene lasts 4 s, at most 20 scenes. An empty script gives one empty scene.
  Keywords, image prompts, caption, hashtags, affiliates and the self-review stay empty, and no
  "Tự tìm ảnh" runs. Everything else is as for any video: pre-render checks, banned-word warnings,
  render and posting. `hand_written` is in the video payload.
- **From a sample video ("Từ video mẫu", [reference.py](../api/src/reels_api/reference.py),
  [routes_references.py](../api/src/reels_api/routes_references.py)):** `POST /api/references/videos`
  takes the topic, the group, the way (`mode`) and either a pasted link, an uploaded file (spooled,
  checked with ffprobe: MP4/MOV/WebM, 3 s to 3 min, 100 MB) or, for `reuse`, a sample learned before;
  it stores the sample row (and the uploaded file), makes the draft video and queues a `learn` job,
  downloading nothing itself. The job prepares the sample once: a link is downloaded (TikTok and
  YouTube through yt-dlp, any other link must be the video file, with the pasted-link rules and a
  100 MB, 180 s limit), up to 16 stills are taken at even steps (540 px wide JPEGs) and the sound goes
  to ElevenLabs Speech-to-Text; no key, a silent sample, or ElevenLabs refusing (a key without the `speech_to_text`
  permission, no quota left, an outage) just leaves the words empty and the job learns from the stills. Then, by way:
  `quick` makes one LLM call with the stills as images that writes the analysis and the script;
  `twostep` analyses first (with the stills; the analysis also describes each still) and writes from
  the analysis without images; `review` analyses and stops, and the member's "Viết kịch bản" (the
  usual `POST /videos/{id}/script`, which queues `learn` for such a video) writes from the analysis as
  edited (`PATCH /api/references/{id}`, refused while one of its videos has a job); `reuse` writes
  from a stored sample, analysing it first only if it never was; `footage` ("Edit từ footage",
  [footage.py](../api/src/reels_api/footage.py)) makes no LLM call: it needs the words (it fails with ElevenLabs'
  reason, or "no key", when there are none), splits them at every pause of 0.45 s or more and every filler
  ("ờ", "à", "ừm"…), splits a stretch over 10 s after the sentence end nearest its middle (else its widest gap),
  pads each stretch (0.12 s before, 0.25 s after, never into a neighbouring word, fillers included; one under
  1 s takes some silence to last 1 s), keeps the first 90 s and cuts each stretch with its sound (AAC) as a
  scene clip with `video_sound` on and its words in the clip's seconds. The first stretch is the title scene,
  its text the topic cut to fit the box; the others have no text box and the words as voice text. The video
  is marked hand-written, narration off, with hard cuts, word captions and ducking; two stretches at least, or
  the job says there is too little speech. When a provider refuses a request
  with images, the job's message says the model may not read images and suggests one that does. After the script is saved, each scene's chosen
  stretch is cut from the stored sample (H.264, no sound, its scene's seconds plus the crossfades and
  2 s spare, at most to the sample's end) and becomes the scene's clip, like an uploaded one; a cut
  that fails leaves the scene to "Tự tìm ảnh", which runs after as for a script. A retry once the
  script is saved does nothing, and a sample already prepared or analysed is never sent again.
  `GET /api/references` lists the samples, `GET /api/references/{id}` gives one with its stills
  (`/frames/<n>.jpg`) and the videos made from it, `DELETE` removes it and its files.
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
  on every request. Three pages need no session: `/login`, `/privacy`, the public privacy policy a
  Meta app needs to go Live, and `/terms`, the public terms of service (exactly those paths; they call no API).
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

### ChatGPT and Claude MCP connection

The optional private MCP endpoint uses member-authorized OAuth delegation, stateless Streamable
HTTP, and the official MCP Python SDK. The web forwards its two exact `.well-known` discovery
paths; `/api/mcp` stays behind the same origin as browser consent. Its bearer credentials do not
work on the normal cookie API, and cookies alone never authenticate MCP. Only the four exact
server protocol POST paths bypass Origin checks; browser consent and revocation keep them.

`mcp_clients` stores registered clients with their allowed callbacks (ChatGPT's, Claude's hosted
one, or Claude Code's loopback one, space-separated); `mcp_authorizations` holds short-lived
session-bound consent tickets and single-use PKCE codes, each with the exact callback it returns to; `mcp_connections` holds scopes,
resource binding, hashed rotating credentials and expiration. Session foreign keys cascade when
the underlying browser login is revoked. Token validation also checks the user's active and
password-change state on every request and tool call.

The tools call the existing video handlers directly, with the authenticated member, storage and
database session. They do not call the HTTP API with manufactured cookies or duplicate business
rules: the product-video tools reuse "Tự viết" video creation, the scene's media-from-link
download, scene creation and the affiliate product list and attachment. Long work still queues
the existing script/render jobs. No publishing, deletion, secret
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
