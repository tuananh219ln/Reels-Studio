# Code Research: ffmpeg-render-worker

Date: 2026-10-28. Scope: greenfield Python render core + CLI (script JSON + scene images + optional
music → 9:16 MP4). No Redis, Postgres, TTS, stock search, or Docker in this feature.

Context7 MCP is configured in `.mcp.json` (`npx -y @upstash/context7-mcp`) but was not reachable
from this research session; library notes in section 9 are from FFmpeg/Pillow reference knowledge
and should be confirmed against the installed versions.

---

## 1. Entry Points

There is **no application code** in the repo. `git ls-files` contains only agent/skill docs,
`.github/workflows/online-pipeline-*.yml`, `.githooks/pre-commit`, `README.md`, `CLAUDE.md`,
`AGENTS.md`, `backlog.md`, `.env.example` (empty), `.gitignore`, `samples/xuong-khop.json`, and
`work/` artifacts. No `pyproject.toml`, `requirements.txt`, `package.json`, `src/`, or `tests/`.

Untracked/ignored leftovers from the Remotion prototype on disk (not in git):

- `node_modules/` (ignored) — Remotion deps, including
  `node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe` (see section 8; unusable).
- `out/xuong-khop.mp4`, `out/frame-45.png`, `out/frame-150.png` (ignored by `out/`) — Remotion
  render output; useful only as a visual reference of the old layout (yellow box, red keyword,
  Be Vietnam Pro 900, white outlined benefit line, number badge, disclaimer pill).

The new feature therefore defines all entry points. The only planned surface is a CLI, e.g.
`python -m <pkg> render <script.json> --out <file.mp4> [--music <file>] [--music-volume 0.25]`
(exact CLI shape is still an open gap in the interview: "Giao diện CLI: tham số, nơi xuất file").

## 2. Data Layer

No database in scope. The only data contract is the script JSON.

### Documented model (architecture.md → Data Model)

- `Video`: chosen title, music track, TTS on/off, content language, etc.
- `Scene`: belongs to Video; `order`, `seconds`, on-screen text with `*red*` keyword markup,
  image prompt/keywords, assigned Asset.
- `RenderJob`: status, timings, output file, error (later feature).

ux-guidelines.md → Video Template:

- 9:16; first frame = thumbnail: close-up food photo full-frame + chosen title in a centered text
  box, 3–5 lines.
- Text box: yellow background + black text (chosen in interview), bold, uppercase, centered,
  `*...*` keywords red.
- Body scenes: one item per scene, 3–5 s each, "the item name plus one benefit line", Ken Burns.
- Font: must render Vietnamese diacritics; default Be Vietnam Pro Black.
- Length: title scene + 5–7 scenes ≈ 20–40 s.

content.md: on-screen text ≤ 10 words per scene; titles ≤ 12 words, uppercase.

### Existing sample: `samples/xuong-khop.json` (old Remotion format)

Fields: `hook {lines[3], seconds:3, emoji}`, `scenes[5] {title, benefit, seconds:4, emoji}`,
`outro {text, seconds:3}`, `disclaimer`. Markup is `**...**` (double asterisk). No `image`
fields, no music. Matching TS types were in `git show 4026e61:src/remotion/schema.ts`
(`image?` was a filename under `public/photos/`, `music?` under `public/music/`,
`musicVolume?` default 0.25).

Conversion facts for the documented format (decision 2 in interview: "Theo tài liệu"):

- `hook.lines` → title scene text (3 lines; `**XƯƠNG CHẮC KHỎE**` → `*XƯƠNG CHẮC KHỎE*`).
- `scenes[].title` + `scenes[].benefit` → one scene text. The documented model has a single text
  field, but the template wants "item name plus one benefit line" → whether the text supports an
  explicit line break (`\n`) or two fields is an **open gap**.
- `emoji`, `outro`, `disclaimer` are dropped (disclaimer is deferred per content.md/backlog).
- Every scene needs an `image` path; the sample has none, so converted sample needs real/sample
  images or the CLI will (correctly) fail with "missing image" for every scene.
- Image path resolution base (relative to JSON file vs CWD) is not yet defined.
- Scene word counts in the sample: e.g. "Cá nhỏ ăn cả xương" + "Giàu canxi, rẻ, dễ tìm" = 10 words
  (at the ≤10 limit).

## 3. Similar Features

Only prior art is the removed Remotion prototype, `git show 4026e61:src/remotion/Reel.tsx`
(256 lines). Layout values that can serve as visual reference (canvas 1080×1920, 30 fps from
`Root.tsx`):

| Element | Value in Reel.tsx |
|---|---|
| Box color / text / keyword | `#FFD60A` / `#111111` / `#E10600` |
| Font | Be Vietnam Pro via `@remotion/google-fonts`, weights 600/800/900, subsets vietnamese+latin; box text weight 900 |
| Title (hook) box | fontSize 96, centered, `paddingTop: 240` offset |
| Item box | fontSize 84 (`titleSize`), placed below a number badge, `paddingTop: 420` |
| Box styling | lineHeight 1.18, padding 30px×44px, borderRadius 22, maxWidth 960, shadow `0 12px 40px rgba(0,0,0,.45)` |
| Benefit line | separate white text, fontSize 58, weight 800, 4px black outline + drop shadow (not in yellow box) |
| Number badge | red circle 150px, white 8px border, white number 96px |
| Ken Burns | scale 1 → 1.12 linear over scene duration, `objectFit: cover` |
| Readability gradient | top 35% black → transparent at 30%, bottom 55% black from 45% |
| Disclaimer | fontSize 30 pill at top (paddingTop 120) — deferred now |
| Music | volume default 0.25, no fade |
| Markup parser | `text.split(/(\*\*.+?\*\*)/)` — non-greedy, no escaping, no nesting |
| Durations | `Math.round(seconds*fps)` per scene, hard cuts (`Series`), no transitions |

Observations from `out/frame-45.png` (title) and `out/frame-150.png` (scene 1): the box wraps
long words to new lines automatically (CSS); at lineHeight 1.18 the stacked diacritics (Ổ in
"TUỔI") nearly touch the line above. Body text in the prototype was in the middle/lower-middle,
not the lower third chosen now. The badge and white benefit line are **not** part of the
documented template (only "item name plus one benefit line" in the yellow box style).

Reference pipeline named in architecture.md: MoneyPrinterTurbo (MIT) — not vendored; any adapted
code must keep MIT attribution in the file header (patterns.md).

## 4. Integration Points

None in code today. Future integration (from architecture.md) that shapes the API of this core:

- `worker` will consume a render job: resolve image (upload or stock search) → TTS → text overlay
  PNG → single FFmpeg graph with music → MP4 into `STORAGE_DIR`, then update `RenderJob`
  (status, timings, output file, error). So the core should be a callable function (inputs →
  output path, raising a typed error), with the CLI a thin wrapper.
- TTS (edge-tts/Azure) later adds a voice audio track into the same mix → audio mixing code
  should allow N audio inputs (`amix`) later.
- Stock image search later fills missing images → "missing image = error" lives in validation,
  before any FFmpeg call.
- Planned env vars (deployment.md): `STORAGE_DIR`, `RENDER_CONCURRENCY` (default 1). None are
  needed for a CLI that takes explicit paths; `.env.example` is empty.

## 5. Existing Tests

No tests, no test framework config, no CI test workflow. The only workflows are the optional
online-pipeline ones (inactive until secrets are configured). patterns.md says:

- Backend: **pytest**.
- **Render smoke test:** render a short MP4 from sample images, assert the file exists and has the
  expected resolution and duration ("guard against silent pipeline breakage").
- Visual template check is manual (a person watches the MP4).
- Quality gates (lint + tests on PRs) are planned, not configured.

test-master smoke guide: keep smoke minimal (import, CLI runs). Suggested test boundaries for this
feature (facts derived from the module split; signatures illustrative):

- Unit (pure, fast): markup parser (`parse_markup("5 *XƯƠNG* KHỎE") -> [(text, is_red)]`,
  unbalanced `*`, uppercase of Vietnamese), script validation (missing image error names the
  scene index/text), timeline math (xfade offsets, total duration), filter-graph string builder
  (input labels, offsets, music vs no-music branch) — no FFmpeg needed.
- Integration (Pillow, no FFmpeg): text box PNG has RGBA mode, transparent outside box, yellow
  inside, red pixels present only when markup present, fits within max width.
- Render smoke (needs FFmpeg; skip with a clear reason if `ffmpeg` not on PATH): synthetic images
  generated by Pillow in `tmp_path`, 2–3 scenes of ~1 s, then `ffprobe` asserts 1080×1920,
  duration ≈ expected (± 1 frame / ~0.1 s), video codec h264/yuv420p, audio stream present only
  when music given.

```python
def test_render_smoke_produces_1080x1920_mp4(tmp_path): ...
def test_missing_scene_image_raises_naming_scene(tmp_path): ...
```

## 6. Shared Utilities

None exist. Utilities the feature will need to create (no reuse candidates in repo):

- Markup parser for `*red*` segments.
- Text layout: word wrap by pixel width (`ImageFont.getlength`), line metrics from font
  ascent/descent rather than glyph bbox.
- Text-box PNG renderer (Pillow, RGBA).
- Timeline calculator (frames per scene, xfade offsets, total duration).
- FFmpeg command builder + subprocess runner (capture stderr, typed error) + `ffprobe` wrapper
  (also reusable by smoke test).
- Binary discovery (`shutil.which("ffmpeg")`, optional `FFMPEG_PATH` override).

## 7. Potential Problems

**Vietnamese text rendering (Pillow)**

- Input may arrive as NFD (combining marks) from some editors/clipboard; Pillow's basic layout
  places combining marks poorly. Normalize with `unicodedata.normalize("NFC", s)`; all Vietnamese
  letters have precomposed code points. `PIL.features.check("raqm")` tells whether complex layout
  is available; it is not required for NFC Vietnamese.
- `str.upper()` handles Vietnamese correctly (ư→Ư, đ→Đ, ế→Ế). Do uppercase after markup parsing
  so `*` positions are unaffected (they are anyway, but keep one pipeline).
- Stacked diacritics (Ổ, Ẫ, Ặ) rise above cap height; computing line height from per-line text
  bbox causes uneven spacing or clipping at the top of the box. Use font metrics
  (`font.getmetrics()`) plus padding; the prototype frame shows diacritics nearly colliding at
  lineHeight 1.18.
- Font file must be shipped explicitly; Windows fonts (Arial, Segoe UI present on host) and a
  slim Linux image differ. No Be Vietnam Pro installed on this host.

**Font licensing**

- Be Vietnam Pro is licensed under the SIL Open Font License 1.1 (Google Fonts /
  github.com/bevietnam/BeVietnamPro). Bundling the TTF in the repo/Docker image is permitted;
  include `OFL.txt` next to it; the font may not be sold by itself. `.gitignore` does not exclude
  `.ttf`. Static `BeVietnamPro-Black.ttf` (weight 900) exists in the family.

**FFmpeg zoompan**

- Jitter: zoompan computes integer x/y crop positions → visible shake on slow zooms. Common
  mitigation: pre-scale the image well above output size (e.g. 2–4× of 1080×1920) before
  zoompan, then output `s=1080x1920`. Trade-off: render time grows with pre-scale size.
- Frame multiplication pitfall: zoompan emits `d` frames **per input frame**. With `-loop 1`
  image input, `d` must be 1 (and duration controlled by `-t`/trim); with a single-frame input
  use `d=<scene_frames>`. Mixing both yields huge/long output.
- Use `on` (output frame index) for deterministic linear zoom, e.g.
  `z='1+0.12*on/<frames>'`, center with `x='iw/2-(iw/zoom/2)'`, `y='ih/2-(ih/zoom/2)'`.
- Aspect: photos are rarely exactly 9:16 → cover-crop first
  (`scale=W:H:force_original_aspect_ratio=increase,crop=W:H`), then `setsar=1`.
- Performance: zoompan is single-threaded per stream; 6–8 parallel chains at high pre-scale on
  the dev host (i7-8700, 6C/12T, 32 GB) may take tens of seconds. No render-time limit is
  defined yet (open gap).
- Very large or EXIF-rotated phone photos: FFmpeg's image2/mjpeg decoder ignores EXIF
  orientation → portrait phone photos can appear rotated. Pre-normalizing with Pillow
  (`ImageOps.exif_transpose`) to a temp JPEG/PNG avoids it.

**xfade offsets**

- For scene durations d0..dn-1 and transition T, offset of transition k (1-based) is
  `sum(d0..d(k-1)) - k*T`; total length = `sum(d) - (n-1)*T`. Without compensation the video is
  shorter than the summed `seconds` and each scene's fully visible time shrinks by T. Decide
  whether to extend each segment by T (keeps total = sum of seconds) — **open gap**.
- xfade requires both inputs with identical resolution, pixel format, frame rate and timebase;
  normalize each chain with `fps=30,format=yuv420p,setsar=1` (and `settb=AVTB` if needed).
  Offsets are in seconds; float rounding should be snapped to frame boundaries.
- xfade needs FFmpeg ≥ 4.3 (Debian bookworm ships 5.1; Ubuntu 22.04 ships 4.4).
- Overlaying each scene's text PNG **before** xfade makes text cross-fade with its photo.

**Audio**

- No music → spec says silent video. Whether "silent" means no audio stream or a silent AAC track
  (`anullsrc`) is undecided; some upload paths/players behave better with an audio track, and
  later TTS mixing will add audio anyway.
- Music shorter than video: "cut to video length" covers longer tracks only; looping
  (`-stream_loop -1`) vs silence padding is undecided.
- Fade: `afade=t=out:st=<total-F>:d=F`, `volume=0.25`, `atrim=0:<total>` and `apad` if needed;
  relying on `-shortest` is fragile with filter graphs; set explicit `-t <total>`.
- Music file formats: any FFmpeg-decodable; corrupt file → FFmpeg error must surface clearly.

**Windows paths and process invocation**

- Paths inside a filter graph (`movie=`, `drawtext fontfile=`) need `:` and `\` escaping
  (`C\:/...`); avoid entirely by passing every image/PNG/music as `-i` inputs and referencing
  `[N:v]`/`[N:a]` labels. Repo path contains a space (`C:\Users\Young Sheldon\...`).
- Use `subprocess.run([...], shell=False)`; never build a shell string (also avoids injection
  from JSON-provided paths).
- Windows command line limit is 32,767 chars; a long graph is unlikely to hit it, but writing the
  graph to a file is safer. FFmpeg 7.x deprecates `-filter_complex_script` in favor of
  `-/filter_complex <file>`; 5.1 (Debian) only supports `-filter_complex_script` — version
  difference between Windows build and Linux image.
- Python on Windows defaults to the ANSI code page for `open()`: always read JSON with
  `encoding="utf-8"` (Vietnamese text otherwise mojibakes; PowerShell 5.1 `Get-Content` shows
  `backlog.md` as mojibake for the same reason). Decode FFmpeg stderr with
  `encoding="utf-8", errors="replace"`.
- Use `pathlib` everywhere; no hard-coded `\` separators so the code runs in the Linux worker.

**Validation / security**

- Missing image → error naming the scene, no render (decided). Same check should cover missing
  music file, unreadable/corrupt image (Pillow `Image.open().verify()`), bad JSON, non-positive
  `seconds`, empty scene list, missing FFmpeg binary (open gap in interview: error_scenarios).
- Unbalanced `*` markup behavior is undefined (literal vs error).
- Text overflow: very long text in a fixed-width box needs a min font size / max lines rule
  (open gap: "Kích thước chữ/độ rộng hộp, xuống dòng khi chữ dài").
- Output overwrite behavior and temp-file cleanup (text PNGs, normalized images) are undefined.

**Docs inconsistency**

- deployment.md says the development host is the owner's Linux machine (i5-10400F, 15 GiB);
  this feature runs on a Windows 10 Pro host (i7-8700, 31.9 GB RAM, ~53 GB free on C:). The
  interview chose native Python + FFmpeg on Windows. deployment.md will need an update at
  finalization.

## 8. Constraints & Infrastructure

**Tool availability on this Windows host (checked 2026-10-28):**

| Tool | Status |
|---|---|
| Python | Not installed. `python`/`python3` resolve to `%LOCALAPPDATA%\Microsoft\WindowsApps` Store stubs ("Python was not found"); no `py` launcher; nothing under `%LOCALAPPDATA%\Programs\Python` |
| pip / uv | Not installed |
| FFmpeg / ffprobe | Not on PATH |
| Remotion-bundled ffmpeg | `node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe` n7.1, built with `--disable-filters` and a whitelist; **no zoompan, xfade, overlay, afade, format**; not usable |
| winget | Available (`winget install Python.Python.3.12`, `winget install Gyan.FFmpeg` are the usual IDs) |
| choco / scoop / docker | Not installed |
| node | `C:\Program Files\nodejs\node.exe` (irrelevant now) |
| git | `C:\Program Files\Git\cmd`, needs PATH refresh in PowerShell |
| Fonts | Arial, Segoe UI present; Be Vietnam Pro absent |

After installing Python via winget, the Store aliases may still shadow it until disabled in
"App execution aliases" or PATH is refreshed.

**Repo conventions:**

- `.gitignore` already ignores `venv/`, `__pycache__/`, `*.pyc`, `out/`, `dist/`, `build/`,
  `tmp/`, `temp/`, `data/`, `.coverage`, `htmlcov/`, `.env*`. It does **not** ignore `.venv/`
  (common default for `python -m venv .venv` / uv) or `.pytest_cache/`. `out/` is the natural
  output dir for CLI renders (already ignored). `samples/` and `work/` are tracked.
- Large binaries: sample photos/music committed to git bloat the repo; tests can synthesize
  images with Pillow and a short tone with FFmpeg `sine`/`anullsrc` instead.
- `.githooks/pre-commit` only syncs `.claude/**` to `.codex/**` and needs
  `~/.claude/scripts/sync-to-codex.sh`; `core.hooksPath` is not set in this clone. Bash script;
  no effect on Python code.
- No CI for lint/tests (planned).
- Git flow: feature branch → PR into `main`; finalize moves feature to `work/completed/`.

**Future Linux worker image:** FFmpeg ships in the worker image (architecture.md). With
`python:3.12-slim` (Debian bookworm) `apt-get install ffmpeg` gives FFmpeg 5.1 (has zoompan,
xfade, libx264, aac). Font must be bundled in repo, not taken from the OS. Code must avoid
Windows-only APIs.

**Output encoding facts (not yet decided in interview — gap "độ phân giải, fps, codec"):**
prototype used 1080×1920 @ 30 fps. Typical Reels-safe output: H.264 (`libx264`), `yuv420p`,
`-movflags +faststart`, AAC 128–192 kbps, CRF ~18–23.

**Recommended project layout (fits the planned `api`/`worker` split):**

```
worker/                         # future Docker build context for the worker service
  pyproject.toml                # deps: Pillow, (pydantic v2 for script schema), pytest
  src/reels_render/
    __init__.py
    script.py                   # load + validate script JSON (NFC, uppercase, path resolution)
    markup.py                   # *red* parsing
    textbox.py                  # Pillow text-box PNG rendering
    timeline.py                 # frames, xfade offsets, total duration
    graph.py                    # pure filter-graph + argv builder
    ffmpeg.py                   # binary discovery, run, ffprobe
    render.py                   # render(script, out_path, music=None, ...) orchestration
    cli.py / __main__.py        # thin argparse CLI
  assets/fonts/BeVietnamPro-Black.ttf, OFL.txt
  tests/ (unit/, test_textbox.py, test_render_smoke.py, conftest.py)
samples/xuong-khop.json         # converted to documented format
```

Font loading via a path relative to the package (`importlib.resources` or `Path(__file__)`),
not CWD.

## 9. External Libraries

**Pillow** (to be added; ≥ 10 recommended):

- `ImageFont.truetype(path, size)`; `font.getlength(text)` for wrap width;
  `font.getmetrics() -> (ascent, descent)` for line height; `font.getbbox(text)`.
- `Image.new("RGBA", (w, h), (0,0,0,0))`; `ImageDraw.Draw(img).rounded_rectangle(xy, radius,
  fill)`; `draw.text((x, y), text, font=font, fill=color, anchor="ls")` — draw per segment for
  mixed black/red runs on one line, advancing x by `getlength`.
- Optional stroke: `draw.text(..., stroke_width=n, stroke_fill=...)` (not needed for the chosen
  yellow-box style).
- `ImageOps.exif_transpose(img)` for phone-photo orientation.
- `PIL.features.check("raqm")` reports complex text layout support.

**FFmpeg** (CLI via subprocess; no Python wrapper needed — `ffmpeg-python` is unmaintained):

- Per scene: `-i <image>` (single frame) →
  `scale=..:force_original_aspect_ratio=increase,crop=..,zoompan=z=..:x=..:y=..:d=<frames>:s=1080x1920:fps=30,setsar=1,format=yuv420p`
  → `[txt]overlay=x=(W-w)/2:y=<Y>` with the text PNG as another `-i`.
- Chain: `[a][b]xfade=transition=fade:duration=T:offset=O` repeated (or `concat` for 0 T).
- Audio: `[m:a]volume=0.25,afade=t=out:st=S:d=F,atrim=0:TOTAL[aout]`; map `-map [vout] -map [aout]`.
- Encode: `-c:v libx264 -pix_fmt yuv420p -r 30 -c:a aac -movflags +faststart -t TOTAL`.
- Probe: `ffprobe -v error -select_streams v:0 -show_entries stream=width,height:format=duration -of json <file>`.
- Graph file: `-filter_complex_script <file>` (5.1) / `-/filter_complex <file>` (7.x).

**pytest** for all tests; mark the FFmpeg smoke test (e.g. `@pytest.mark.skipif(shutil.which("ffmpeg") is None, ...)`)
so unit tests run without FFmpeg.

---

## Open Gaps Surfaced by Research (for the interview)

1. Output spec: 1080×1920 @ 30 fps, H.264/AAC, CRF — confirm.
2. Title scene: its own image (thumbnail photo) and its seconds — required fields?
3. Scene text: one field with line break vs separate `name` + `benefit`; number badge (prototype
   had one) yes/no.
4. Crossfade compensation: keep total = sum(seconds) or let it shrink by (n-1)×T.
5. No music: no audio stream vs silent AAC track; music shorter than video: loop vs pad.
6. Image path base (relative to JSON dir?), output path default, overwrite policy.
7. Text sizing: font sizes, box max width (prototype 960 px), max lines, auto-shrink on overflow;
   lower-third exact Y and safe zones for Reels UI (bottom ~20% covered by caption/buttons).
8. Font: bundle `BeVietnamPro-Black.ttf` + OFL in repo (recommended) vs system install.
9. Render-time budget and Ken Burns direction (always zoom-in vs alternate in/out/pan).
10. Sample assets for `xuong-khop.json` and the smoke test: synthetic vs real photos (git size).
