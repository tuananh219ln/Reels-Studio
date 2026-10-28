# Code Research: stock-image-search

Date: 2026-10-28. Scope: the scene `keywords` field, an automatic Pexels → Pixabay photo search
when a scene's `image` is empty, absent or missing, a terminal fallback prompt, and `.env`
loading, all in the `reels_render` render core and CLI.

Sources: repo files at `main` (clean); Pexels docs (https://www.pexels.com/api/documentation/)
and Pixabay docs (https://pixabay.com/api/docs/), both fetched 2026-10-28. Context7 was not used.
The feature needs no library beyond the Python stdlib (see section 9).

---

## 1. Entry Points

- `worker/src/reels_render/cli.py`: `main(argv: list[str] | None = None) -> int`. It reconfigures
  stdout and stderr to UTF-8, then parses `script`, `-o/--output` (required), `--music` and
  `--music-volume`. It calls `load_script(args.script)` and then
  `render_video(script, args.output, music=..., music_volume=...)`. On any `RenderError` it
  prints `Lỗi: {err}` to stderr and returns 1. On success it prints `Đã render: {output}` and
  `Thời gian render: X.Xs`. The CLI is the only place where an interactive `input()` prompt
  belongs. There is no `isatty`, `input(`, `os.environ` or `getenv` anywhere in the package today.
- `worker/src/reels_render/__main__.py`: `sys.exit(main())`. Usage:
  `python -m reels_render script.json -o out.mp4`.
- `worker/src/reels_render/script.py`:
  - `load_script(path: Path) -> Script` reads UTF-8 JSON and calls `parse_script`.
  - `parse_script(data: object, base_dir: Path) -> Script`.
  - `_parse_scene(item: object, label: str, base_dir: Path) -> Scene`.
  - Labels are `"Cảnh tiêu đề"` for the title and `"Cảnh {n}"` for content scenes (1-based).
- `worker/src/reels_render/render.py`:
  `render_video(script, output, music=None, music_volume=0.25) -> Path`. This is the public
  callable that the future worker will use.
- `worker/src/reels_render/__init__.py` re-exports `render_video`, `load_script`, `Scene`,
  `Script`, `DEFAULT_MUSIC_VOLUME` and the five error classes. New public names, such as a new
  error type or a resolver function, would be added to `__all__` here.

## 2. Data Layer: script JSON contract (current)

There is no database. The script is a JSON file shaped like this (see
`samples/xuong-khop.json`):

```
{ "title": {"text", "seconds", "image"}, "scenes": [ {"text", "seconds", "image"}, ... ] }
```

`script.py` dataclasses (both frozen):
- `Scene(label: str, lines: list[list[Run]], seconds: float, image: Path)`. `image` is an
  absolute-or-joined `base_dir / image` path, and today it is guaranteed to be an existing file.
- `Script(title: Scene, scenes: list[Scene])` with the property `all_scenes = [title, *scenes]`.

`_parse_scene` validation order is:
1. The scene is a dict.
2. Each of `text`, `seconds` and `image` is present. A missing key raises
   `{label}: thiếu trường "image"`.
3. `text` is a string.
4. `seconds` is a number that is not a bool, is finite, is at most 1e9 and is at least 1.
5. `image` is a string. Otherwise it raises `"image" phải là chuỗi đường dẫn ảnh`.
6. `image` is not blank. Otherwise it raises `thiếu ảnh ("image" đang trống)`.
7. The text markup parses.
8. `(base_dir / image).is_file()`. Otherwise it raises `không tìm thấy file ảnh {path}`.

Unknown keys, such as a future `keywords`, are ignored today; no unknown-key check exists.

Places this feature has to change:
- Steps 2, 6 and 8 are currently hard `InputError`s. The feature turns absent, empty and
  missing-file `image` values into "needs search", with a warning when the file is missing.
- `Scene.image: Path` can no longer be guaranteed at parse time. Options are `Path | None` plus
  `keywords: tuple[str, ...]`, or a separate resolution step that runs before
  `render_video` / at its start.
- `keywords` validation is new: a list of non-empty strings. Pixabay's `q` is limited to 100
  characters (section 9).
- The JSON writeback when the user supplies a manual image is new. Today nothing ever writes the
  script file; `load_script` only reads it, and `Script` keeps no source path or raw data. A
  writeback needs the source JSON path plus the raw dict (or a re-read) so that it updates only
  `image` of one scene. It should keep `ensure_ascii=False`, because the text is Vietnamese.
  Formatting and key order of the hand-written sample would be lost by `json.dumps`.

## 3. Similar Features / Patterns to Reuse

- **Typed errors with Vietnamese messages that name the scene.** Every message is prefixed with
  `{scene.label}: `, and tests assert `str(err).startswith("Cảnh 3: ")`.
- **Tool discovery as a typed error.** `ffmpeg.find_tools()` raises `ToolNotFoundError` with an
  install hint. A missing API key can follow the same pattern, with a hint naming `.env` and the
  variables.
- **Intermediates in the temp dir.** `render_video` uses
  `tempfile.TemporaryDirectory(prefix="reels_render_")`. It writes `scene-{i:02d}.jpg` (via
  `normalize_image`) and `text-{i:02d}.png` there. Downloaded stock images would fit there too, for
  example as `stock-{i:02d}.<ext>`, and then go through `normalize_image` like user images.
  `normalize_image` applies `ImageOps.exif_transpose` and converts to RGB JPEG q95, so it already
  copes with JPEG, PNG or WebP downloads. It raises
  `InputError("{label}: ảnh hỏng hoặc không đọc được ...")` for corrupt bytes.
- **Validation before FFmpeg.** Text layout (`TextFitError` → `InputError`) runs before the temp
  dir is opened. `normalize_image` runs inside the temp dir but before `ffmpeg.run`. Network
  search therefore must finish, or fail, before `ffmpeg.run` is called. That way a failed search
  never leaves a temp output file.
- **Monkeypatch seams.** Tests patch `reels_render.ffmpeg.shutil.which`, `reels_render.ffmpeg.run`,
  `render_module.os.replace` and `tempfile.tempdir`. A small module-level HTTP function, such as
  `stock._get(url, headers, timeout) -> bytes`, gives the same kind of seam for mocking the
  network.
- **MoneyPrinterTurbo** has a "material search" module that `architecture.md` says may be
  adapted. If any code is adapted, MIT attribution in the file header is required
  (`patterns.md`). That code is not in this repo.

## 4. Integration Points

Proposed resolution step, between parse and render:

```
cli.main → load_script(path) → [NEW resolve images: per scene with no usable image →
  keywords loop → Pexels → Pixabay → download to work dir] → render_video(...) → normalize_image
  → graph → ffmpeg.run → _publish
```

- **Temp dir lifetime.** The temp dir is created inside `render_video`. If search happens inside
  `render_video`, downloads can live in the same `work_dir`, so cleanup is automatic. If search
  happens before `render_video` (for example in the CLI or a separate function), the caller must
  own another temp dir, or `render_video` must accept already-resolved paths.
- **Interactive fallback ordering.** The CLI prompt must run before FFmpeg. It also copies the
  file next to the JSON and writes the JSON, and that should happen before the output temp file
  is created. A clean split is a core function that raises a typed error listing the unresolved
  scenes; the CLI catches it, prompts, updates the JSON, resolves again or reloads, and then
  renders. Non-interactive callers just get the error.
- **Missing-file warning.** The warning is a new output channel. The core prints nothing today
  (only the CLI prints). Options: a `warnings`/callback parameter, the `logging` module, or
  returning warnings from the resolver for the CLI to print to stderr.
- **Env.** `PEXELS_API_KEY` and `PIXABAY_API_KEY` are read from `os.environ`, after an optional
  load of the repo-root `.env`. The repo root is `worker/..`. With an installed package,
  `Path(__file__)` is `worker/src/reels_render/...`, so the root is `parents[3]`. Alternatives are
  a `.env` in the CWD, or one found by walking up from the script JSON. The CLI tests run with
  `cwd=tmp_path`, so a CWD-based lookup would not pick up the developer's real `.env` in tests,
  but a `__file__`-based lookup would. Tests must clear or patch the env either way.

## 5. Existing Tests

The framework is pytest 9.2 (dev extra). Run it from `worker/` (`testpaths = ["tests"]`). The
venv `worker/.venv` has Python 3.12.10 with Pillow 13.0.0 and pytest; requests and httpx are not
installed.

- `tests/conftest.py` helpers:
  - `make_image(path, size, color)` creates a Pillow image.
  - `write_script(dir, data) -> script.json` writes with `ensure_ascii=False`.
  - `scene(text, seconds, image="a.jpg") -> dict`.
  - `script_data(scene_count, **title)`.
  - `needs_ffmpeg` is a skip marker. Also present: `extract_frame`, `mean_volume`, `make_tone`.
- `tests/test_script.py` is a parametrized table of scene errors. It currently asserts these
  behaviors that the feature changes:
  - `({"image": ""}, "thiếu ảnh")`
  - `({"image": "khong-co.jpg"}, "không tìm thấy file ảnh")`
  - `test_title_errors_name_title` expects `Cảnh tiêu đề: thiếu trường "image"`.
- `tests/test_cli.py::test_missing_image_exits_non_zero_and_names_scene` runs the CLI as a
  subprocess (`sys.executable -m reels_render`) and expects a non-zero exit with
  `"Cảnh 2: không tìm thấy file ảnh"`. Under the new behavior this goes to a search plus a
  warning, so the test must change. A subprocess CLI test also cannot use monkeypatch for HTTP,
  and stdin is not a TTY there, so the prompt path must be tested by calling `main()` in-process
  with patched `input`/`sys.stdin`, or by feeding stdin.
- `tests/test_render_smoke.py` has the pattern "rejected before FFmpeg":
  `monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: pytest.fail("FFmpeg must not run"))`,
  plus `isolated_tmp`, which redirects `tempfile.tempdir` to detect leftovers.
- `tests/test_images.py` and `tests/test_textbox.py` are pure unit tests.

Representative signatures:
- `def test_scene_errors_name_the_scene(folder, override, message)`
- `def test_broken_image_reported_before_ffmpeg_and_output_untouched(tmp_path, monkeypatch)`

No network tests exist, and none should hit the real APIs by default. HTTP can be mocked by
patching the module's fetch function, or `urllib.request.urlopen`. Fake response bodies can be
JSON plus small Pillow-generated JPEG bytes.

## 6. Shared Utilities

- `images.normalize_image(source, target, label)` validates and normalizes any image into a JPEG.
  It can double as the "is this download a real image" check.
- `errors.py`:
  - `RenderError` is the base class.
  - `InputError`, `ToolNotFoundError` and `FFmpegError(message, stderr_tail)`.
  - `OutputNotReplacedError(message, kept_path)` is the precedent for an error carrying extra
    typed data. A "missing images" error could similarly carry the list of scene labels.
- `graph.py` scales every image to cover `FRAME_WIDTH*PRESCALE × FRAME_HEIGHT*PRESCALE` with
  `force_original_aspect_ratio=increase` and then crops. Any aspect ratio works, but
  low-resolution sources (for example Pixabay `webformatURL` at 640 px max) are upscaled and look
  soft. The frame is 1080×1920 (`textbox.FRAME_WIDTH/HEIGHT`).

## 7. Potential Problems

- **Documentation contradictions:**
  - `architecture.md` › Render Core says: "**Missing image is an error.** There is no placeholder
    background; stock search will fill images later." The script input description lists `image`
    as required.
  - `architecture.md` › External Integrations says for Pexels and Pixabay: "Store source and
    license info on the asset." This conflicts with the decision to store no credit or
    attribution.
  - `architecture.md` › Render pipeline step 1 and Data Flow step 5 place image resolution in the
    worker. This is consistent, but the render core and CLI now do it too.
  - `content.md` › Script Generation Contract item 4: the 9:16 image prompt per scene "doubles as
    the stock-search keywords" in the MVP. This differs from a separate English `keywords` list.
  - `content.md` › Original content: stock images are "a fallback" and own photos are preferred.
    This is consistent (`image` set → user photo wins).
  - `deployment.md` lists `PEXELS_API_KEY` and `PIXABAY_API_KEY` as "planned, finalized at
    scaffold time" and says `.env.example` is empty. This feature would be the first to fill it.
  - `patterns.md`: "Provider choice is configuration ... the stock image source". A hard-coded
    Pexels-then-Pixabay order partly contradicts this.
  - `ux-guidelines.md` and the planned web UI are unaffected.
- **Provider terms vs. "no attribution".** Pexels guidelines ask for a prominent Pexels link and
  photographer credit "when possible". Pixabay asks that images be downloaded, not hot-linked
  (which this design satisfies). Its "requests must be cached for 24 hours" rule conflicts with a
  "fresh random result on every render" policy if the same query repeats within 24 h.
- **Rate limits.** Pexels allows 200 requests/hour and 20,000/month. Each keyword tried costs one
  request per provider, so a 6-scene script with 3 keywords each needs up to 36 search requests.
  Pexels sends `X-Ratelimit-*` headers only on 2xx responses, not on 429. Pixabay allows 100
  requests per 60 s per key and returns 429 `API rate limit exceeded`.
- **User-Agent blocking (unverified).** CDN hosts (`images.pexels.com`, `pixabay.com`) are
  commonly reported to answer 403 to urllib's default `Python-urllib/3.x` User-Agent. A custom
  `User-Agent` header avoids this. Verify with a live request.
- **Secrets.**
  - The Pixabay key goes in the query string (`?key=`), so error messages, logs and exception
    reprs (`urllib.error.HTTPError.url`, `str(err)`) can leak it. Strip it before printing.
  - The Pexels key goes in the `Authorization` header and is safe from URL leakage.
  - `.env` is already gitignored (`.env`, `.env.*`, `!.env.example`).
- **Downloaded content is untrusted.** Check the `Content-Type` and size; cap bytes read so a
  huge body cannot fill memory or disk. Pillow `DecompressionBombError` is already caught in
  `normalize_image`. Never use the remote file name as a path; generate names.
- **Randomness and tests.** "Fresh random result each render" needs an injectable
  `random.Random`/seed, or a patchable choice, for deterministic tests.
- **Interactive prompt edge cases (Windows).**
  - Explorer drag-drop into the classic console or Windows Terminal pastes the path. In cmd it is
    wrapped in `"..."` only if it contains spaces.
  - PowerShell pastes `'C:\path with space\a.jpg'`, and sometimes `& 'C:\...'` when the drop
    starts the line.
  - Trailing spaces or newlines may appear. Strip whitespace, then one leading `& `, then matching
    surrounding `'` or `"`.
  - The user's home path contains a space (`C:\Users\Young Sheldon`), so quoting is the normal
    case here.
  - Typing `exit`/an empty line, Ctrl+C (`KeyboardInterrupt`) and `EOFError` must be handled.
  - `input()` prompts go to stdout, which `main` reconfigures to UTF-8; Vietnamese prompt text is
    fine.
  - Detect interactivity with `sys.stdin.isatty()`.
- **Copying the manual image next to the JSON.**
  - Possible name collisions: the destination file already exists, or the source already lives in
    that folder.
  - The JSON stores a path relative to the JSON directory, with forward slashes for portability
    (the sample uses `xuong-khop/00-tieu-de.jpg`).
  - Write the JSON atomically (temp file plus `os.replace`, as `_publish` does) so a crash cannot
    corrupt the script.
- **Partial progress.** The interview's earlier answer (7b, "keep images already found") conflicts
  with the later "don't write found images back" (11). Downloaded images are temporary and
  re-searched on the next run.
- **Network timeouts.**
  - `urllib.request.urlopen(req, timeout=...)` raises `URLError`, `TimeoutError`/`socket.timeout`
    or `HTTPError`; `http.client.IncompleteRead` and `ConnectionResetError` can also occur.
  - On Python 3.12 `socket.timeout` is an alias for `TimeoutError`.
  - SSL errors come as `URLError(reason=ssl.SSLError)`.
  - All of these should map to "try next keyword/provider", or for no network at all, a typed
    error.
  - The timeout covers each blocking socket operation, not the whole download. A total deadline
    needs a manual check.

## 8. Constraints & Infrastructure

- Python is `>=3.12` (venv 3.12.10). The only runtime dependency is `Pillow>=10`, and the dev
  extra is `pytest>=8`.
- The dev host is Windows 10. The repo path contains a space. FFmpeg comes from winget.
- The render budget is no more than 2× the video length (`deployment.md`). Does network download
  time count? It is not stated; the CLI prints the total time, including search, if search is
  inside the timed block.
- There is no CI yet; the GitHub Actions quality gates are "planned, not configured". The
  pre-commit hook (`.githooks/pre-commit`) only syncs `.claude/**` to `.codex/**`/`AGENTS.md`, so
  any Project Knowledge edits trigger that sync.
- `.env.example` exists at the repo root and is empty (0 bytes). `.env` is not present in git.
- The future Linux worker will call `render_video` non-interactively, so the core must never call
  `input()`.

## 9. External Libraries / APIs

**HTTP: stdlib `urllib.request` is enough.** You need `Request(url, headers=...)`,
`urlopen(req, timeout=...)`, `json.load(resp)`, `urllib.parse.urlencode` and `quote`. These avoid
adding requests or httpx (neither is installed). TLS uses the OS cert store via `ssl`. On Windows,
Python 3.12 loads system root certificates.

**`.env` loading.** python-dotenv is not installed. A minimal stdlib parser is enough:
- read lines;
- skip blanks and `#` comments;
- split on the first `=`;
- strip whitespace and matching quotes;
- strip an optional `export ` prefix;
- read the file as UTF-8 and handle a BOM, because PowerShell `Out-File` writes UTF-8 with a BOM.

Real environment variables should win, as python-dotenv does by default (`override=False`).

**Pexels.**
- Endpoint: `GET https://api.pexels.com/v1/search`. The header is `Authorization: <API_KEY>`, with
  no "Bearer" prefix.
- Search params:
  - `query` (required).
  - `orientation` = `landscape|portrait|square`.
  - `size` is a minimum size: `large` (24MP), `medium` (12MP) or `small` (4MP).
  - Also `color`, `locale` (e.g. `en-US`), `page` (default 1) and `per_page` (default 15,
    max 80).
- Response:
  - `photos[]`, `page`, `per_page`, `total_results`, and optional `next_page`/`prev_page`.
  - Each photo has `id`, `width`, `height`, `url`, `photographer`, `photographer_url`,
    `photographer_id`, `avg_color`, `alt` and `src{}`.
- `src` variants:
  - `original` at full `width`×`height`;
  - `large2x` and `large` (940×650 at DPR 2 and DPR 1);
  - `medium` (350 px tall) and `small` (130 px tall);
  - `portrait` (cropped to 800×1200);
  - `landscape` (1200×627) and `tiny` (280×200).
  - For a 1080×1920 frame, `portrait` (800×1200) is upscaled. `original` is full-size and may be
    many MB.
  - Unverified, not in the docs: `src` URLs accept query params such as
    `?auto=compress&cs=tinysrgb&w=1080&h=1920&fit=crop`. Verify live before relying on it.
- Rate limit: 200/hour and 20,000/month. The headers `X-Ratelimit-Limit`,
  `X-Ratelimit-Remaining` and `X-Ratelimit-Reset` (a UNIX timestamp) are sent on 2xx only. 429
  means over the limit.
- Guidelines: show a "Photos provided by Pexels" link, and credit photographers when possible.
  Do not replicate Pexels' core functionality.

**Pixabay.**
- Endpoint: `GET https://pixabay.com/api/?key=<KEY>&q=<urlencoded, ≤100 chars>`.
- Params:
  - `lang` (default `en`);
  - `image_type` = `all|photo|illustration|vector`; use `photo`;
  - `orientation` = `all|horizontal|vertical`; use `vertical`;
  - `min_width`, `min_height` (default 0);
  - `safesearch` (default `false`);
  - `order` = `popular|latest`;
  - `page`;
  - `per_page` from 3 to 200 (default 20).
- Response: `total`, `totalHits` and `hits[]`. Each hit has `id`, `pageURL`, `tags`,
  `imageWidth`, `imageHeight`, `previewURL`, `webformatURL`, `largeImageURL` and `user`.
- Image URLs:
  - `webformatURL`: max 640 px. Replace `_640` with `_180`/`_340`/`_960` for other sizes. It is
    valid for 24 h.
  - `largeImageURL`: max 1280 px. This is the best size available to a standard key.
  - `fullHDURL` (1920 px) and `imageURL` (original) require approved full API access and are
    absent otherwise.
- Rules:
  - "Permanent hotlinking is not allowed ... download them to your server first."
  - "Requests must be cached for 24 hours."
- Rate limit: 100 requests per 60 s per key. The headers are `X-RateLimit-Limit`,
  `X-RateLimit-Remaining` and `X-RateLimit-Reset` (seconds).
- Errors: an HTTP status with a plain-text body. 429 returns "API rate limit exceeded". The
  response for an invalid key is not documented; in practice it is a 4xx with a text body. Expect
  a non-JSON body on errors.

**Python stdlib notes relevant here.**
- `random.Random(seed).choice(...)` gives an injectable choice.
- `shutil.copy2` copies the manual image.
- `os.replace` gives an atomic JSON write.
- `sys.stdin.isatty()` detects interactivity.
- `input()` raises `EOFError` on closed stdin.
- `tempfile` is already used.
