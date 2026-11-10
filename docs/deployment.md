# Deployment & Operations

## Current State

Development runs locally (below). Production runs at reels.quangdang.xyz; its one-time setup is in
the README ("Triển khai (CI/CD)").

**Development host:** a Windows 10 Pro machine (Intel i7-8700). The render core runs natively,
without Docker: Python 3.12 and FFmpeg are installed with winget (`Python.Python.3.12`,
`Gyan.FFmpeg`), and the package is installed into `worker/.venv`. If `python` opens the Microsoft
Store, disable the alias under "App execution aliases" or call the installed interpreter
directly.

Postgres runs in Docker (Docker Desktop with WSL2) via `docker compose up -d postgres`; `api`, the
worker, and `web` run natively in development, and the api venv also installs `../worker`. On the
first start of an empty volume,
`docker/postgres-init/` creates `reels_test` (pytest) and `reels_e2e` (Playwright) next to the dev
database. Use `127.0.0.1` rather than `localhost` in local URLs: on this host `localhost` tries IPv6
first and adds a 5-second delay. The setup commands are in the README.

**macOS/Linux:** `scripts/dev.sh` does the whole local start in one terminal (needs uv, Docker, Node
and FFmpeg): Postgres, `.env` from `.env.example` if missing, `api/.venv` rebuilt with uv on the
Python in `.python-version` whenever it is missing, on another Python, built for another folder or
behind a `pyproject.toml`, `alembic upgrade head`, `npm install` when the lock file changed, then api
(auto-reload), worker and web with labelled output. Ctrl+C, or any one of them stopping, stops all
three. The compose project is named `reels-studio`, so moving the repo keeps the same database.

**Render budget:** rendering must take no longer than 2× the video length on this host.

## Production

| Part | Where | How it is built |
|---|---|---|
| `api` | Coolify application, Dockerfile build pack, base directory `/`, Dockerfile `/api/Dockerfile` | Coolify builds [api/Dockerfile](../api/Dockerfile) from git; it installs FFmpeg to check scene clips |
| worker | Coolify application, base directory `/`, Dockerfile `/api/Dockerfile.worker`; no domain | Coolify builds [api/Dockerfile.worker](../api/Dockerfile.worker) (the api image plus FFmpeg, and Node 22 with the pinned HyperFrames CLI, GSAP and its headless Chrome for "Cảnh động"; the build renders a short test scene. It also installs `onnxruntime` and downloads the LaMa model (about 200 MB) and PP-OCRv4's text detector (about 5 MB) of "Sửa ảnh", each at a pinned revision and SHA-256 checked, then erases a test box and finds test words with them) |
| storage | Host folder `/data/reels-storage`, owned by uid 10001, mounted at `/data/storage` in both the api and the worker | Created once by hand on the server |
| `postgres` | Coolify standalone PostgreSQL 17, database `reels`, not public | Not redeployed by CI; Coolify Scheduled Backups |
| `web` | Cloudflare Workers, worker `reels-studio-web` ([web/wrangler.jsonc](../web/wrangler.jsonc)) | `@opennextjs/cloudflare` in GitHub Actions |

- **Images build from the repo root** ([.dockerignore](../.dockerignore)), because both
  install `worker/` (`reels_render`) next to `api/`. Both run as uid 10001.

- **Why Workers, not Pages:** the web app needs a server runtime for `proxy.ts` and the `/api/*`
  rewrite. Cloudflare runs full Next.js through OpenNext on Workers; the old Pages adapter is
  deprecated. Next.js 16's `proxy.ts` is Node middleware, which OpenNext Cloudflare supports only
  as experimental: the build prints a warning. Keep `proxy.ts` to a cookie check.
- **One origin is kept:** the worker forwards `/api/*` to `API_URL` (the Coolify api domain),
  baked in at build time. The browser only talks to the web domain, so the session cookie stays
  first-party. The api's own domain is public too; the `Origin` check still guards it.
- **Static assets:** the worker does not run in front of them, so `next.config.ts` headers do not
  apply; [web/public/_headers](../web/public/_headers) makes `/_next/static/*` immutable for a year
  (Cloudflare's default is `max-age=0, must-revalidate`, one revalidation per file per page load).
- **Delivery:** [.github/workflows/ci-cd.yml](../.github/workflows/ci-cd.yml). Every PR
  runs api pytest with FFmpeg on four machines at once, each taking every 4th test (`PYTEST_SHARD`,
  see `api/tests/conftest.py`; a skipped test fails the job), both Docker
  image builds and the render parity test inside the worker image, worker pytest with FFmpeg, web
  typecheck + lint + Cloudflare build, and E2E (with a real worker and fake Claude/Pixabay) on four
  machines at once, each taking every 4th test of `playwright test --list`. A draft PR runs only the
  quick jobs (api, worker, web); E2E and the image job run once it is ready for review, and the quick
  jobs run again then only if they did not pass on that commit. When they are skipped, the
  `api-passed` job reports `api (1)`…`api (4)` as passed, since `main`'s ruleset requires those
  exact names and a skipped matrix job reports only `api`. A PR that changes only `docs/` or
  `.md` files runs no CI. A push to `main` runs every job, unless its files are exactly the merged
  PR's last commit and every check passed there (the `passed` job; `main` requires PRs to be up to
  date before merging, so this holds for a merge, squash or rebase). Then, with every check passed,
  it deploys in order, each waiting for Coolify to report `finished`: the api (it runs the
  migrations), then the worker, then `npm run deploy` in `web/`. Coolify auto-deploy must stay off,
  or a push deploys before the tests pass.
- **CI broken by GitHub:** during a GitHub Actions incident a run can end as failure without creating
  some of its jobs, and the required checks it never created stay "Waiting for status".
  [.github/workflows/ci-rerun.yml](../.github/workflows/ci-rerun.yml) runs every 20 minutes and reruns,
  once, the newest CI/CD run of `main` or an open PR that failed with no job failing (script:
  [.github/scripts/rerun-stalled-ci.sh](../.github/scripts/rerun-stalled-ci.sh), `DRY_RUN=1` to try it
  locally). A run with a failing test is never rerun; one already rerun is rerun by hand ("Re-run all
  jobs", not "Re-run failed jobs").
- **Database URL:** the api's `DATABASE_URL` is the Postgres internal URL Coolify shows
  (`postgres://…`); `config.database_url()` rewrites a driverless `postgres://`/`postgresql://`
  scheme to `postgresql+psycopg://`.
- **Migrations** run in the api container on every start (`alembic upgrade head`), before uvicorn.
  Write migrations so the previous api and worker versions keep working until the whole deploy
  finishes. A new job kind is only understood once the new worker is up: one queued in between
  fails and needs "Thử lại".
- **GitHub environment `production`:** secrets `COOLIFY_WEBHOOK` (api), `COOLIFY_WORKER_WEBHOOK`,
  `COOLIFY_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`; variable `API_URL`.
- **Rollback:** api or worker — redeploy an earlier deployment in Coolify; web — `npx wrangler
  rollback` in `web/` or the Workers dashboard. A rollback does not revert migrations.
- **Checked by hand after infrastructure changes** (only real infrastructure shows them): MP4
  seeking through Cloudflare (Range requests), a photo uploaded through the api appearing in a
  worker render (shared storage), and render time on the VPS.

## Environment Variables

**See:** [.env.example](../.env.example); keep this table in sync with it. The api, the
worker, and the render core read `.env` at the repo root; a real environment variable wins, even
when set to an empty string. Containers use real environment variables only.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | worker and api: Claude API, used when no Claude key is saved on Cài đặt › Mô hình AI (keys for other LLM providers are entered only there) |
| `CLAUDE_MODEL` | worker and api: Claude's model when none is set on Cài đặt › Mô hình AI; the default is `claude-sonnet-5-5` |
| `PIXABAY_API_KEY` | api: the scene picker's default stock source (and the render core CLI); a key pasted on Cài đặt › Nguồn tư liệu wins over it |
| `PEXELS_API_KEY` | optional, api: a second picker source (locale vi-VN); without it (or a key pasted on Cài đặt › Nguồn tư liệu) the picker hides Pexels. Openverse needs no key |
| `UNSPLASH_ACCESS_KEY` | optional, api: Unsplash's Access Key (free "demo" plan, 50 searches an hour for the team); a key pasted on Cài đặt › Nguồn tư liệu wins. Without either, the picker shows Unsplash greyed out ("chưa cấu hình key") and searching it says so. Wikimedia Commons needs no key |
| `WIKIMEDIA_API_URL`, `UNSPLASH_API_URL` | tests and E2E only: point the two sources at `api/scripts/fake_services.py`; unset in production |
| `OPENVERSE_CLIENT_ID`, `OPENVERSE_CLIENT_SECRET` | optional, api: a registered Openverse application for its higher rate limits; without them Openverse is called anonymously, and a failed token exchange falls back to anonymous |
| `STORAGE_DIR` | api and worker: the shared files folder; `/data/storage` in production, `data/storage` at the repo root when empty |
| `DATABASE_URL` | api and worker: dev database; in production the Coolify Postgres internal URL |
| `TEST_DATABASE_URL` | api: pytest database `reels_test` |
| `ALLOWED_ORIGINS` | api: comma-separated origins allowed to change data; the default is `http://localhost:3000`; in production the web domain |
| `MCP_PUBLIC_URL` | api, optional: public web URL ending in `/api/mcp`; enables private ChatGPT and Claude MCP/OAuth. Empty disables it. HTTPS required except localhost; the origin must be in `ALLOWED_ORIGINS`. See [chatgpt.md](chatgpt.md) |
| `REELS_SERVER`, `REELS_NODE_TOKEN` | render machine only (`python -m reels_api node` on a member's computer), never the api or the worker: the web address and the machine's token from Cài đặt › Máy render. `api/scripts/render-node.ps1` sets both for its run. See [Render machine](#render-machine) |
| `COOKIE_SECURE` | api: `true` adds the Secure flag to the session cookie; set on the Coolify application, empty on localhost |
| `ELEVENLABS_API_KEY` | api + worker: scene narration and the voice list; a key pasted on Cài đặt › Nguồn tư liệu wins over it; with neither, a render with voice text fails with a clear reason |
| `VIENEU_API_KEY` | api + worker, optional: VieNeu's Vietnamese narration voices (`vn_sk_…`, from VieNeu's Nhà phát triển page); a key pasted on Cài đặt › Mô hình AI wins over it. With a key, VieNeu's voices join the voice picker beside ElevenLabs'; a video whose voice is a VieNeu one (`vieneu:<name>`) is read by VieNeu |
| `IMAGE_GEN_API_KEY` | worker: AI photos for scenes that have none (Gemini via Google AI Studio); a key pasted on Cài đặt › Nguồn tư liệu wins over it; with neither, an image job fails with a clear reason |
| `IMAGE_GEN_MODEL` | worker, optional: the image model; the default is `gemini-2.5-flash-image` |
| `IMAGE_GEN_PROVIDER` | api + worker, optional and kept for older servers: the team's default AI photo provider until one is chosen on Cài đặt › Nguồn tư liệu (`gemini` or `cloudflare`; any other value means `gemini`). Unset: Cloudflare when it is set up, else Gemini |
| `IMAGE_GEN_CF_API_KEY` | api + worker: Cloudflare Workers AI API token; a token pasted on Cài đặt › Nguồn tư liệu wins over it |
| `IMAGE_GEN_CF_ACCOUNT_ID` | api + worker: the Cloudflare account ID (dashboard, top right; not a secret), needed with `cloudflare`. Without it on the api, Cài đặt › Nguồn tư liệu shows Cloudflare as not set up even with a pasted token |
| `IMAGE_GEN_CF_MODEL` | worker, optional: the Workers AI model; the default is `@cf/black-forest-labs/flux-1-schnell` |
| `IMAGE_INPAINT_CF_MODEL` | worker, optional: the Workers AI inpainting model of "Sửa ảnh" › "Xóa vùng" with Cloudflare (same token and account); the default is `@cf/runwayml/stable-diffusion-v1-5-inpainting` |
| `TEXT_DETECT_MODEL_PATH` | worker: PP-OCRv4's text detector (ONNX) of "Sửa ảnh" › "Tìm chữ/logo tự động". Set by [api/Dockerfile.worker](../api/Dockerfile.worker) to the file it bakes in (`/opt/lama/text_detect.onnx`); nothing to set on Coolify. Empty or missing: the job fails and the member draws the boxes by hand |
| `LAMA_MODEL_PATH` | worker: the LaMa ONNX model of "Sửa ảnh" › "Xóa vùng" (free, on the worker's CPU). Set by [api/Dockerfile.worker](../api/Dockerfile.worker) to the file it bakes in (`/opt/lama/lama_fp32.onnx`); nothing to set on Coolify. Empty or missing: a LaMa job fails and says to pick Cloudflare |
| `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL` | api and worker, optional, same values on both (the api recognizes made narration and the MP4 fingerprint by them): the voice (default "Adam", `pNInz6obpgDQGcFmaJgB`) and model (default `eleven_v3`); changing either re-makes every narration on the next render |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | api + worker: the TikTok developer app's Client Key and Secret (Login Kit + Content Posting API), the app's identity and not a member's; members connect their own TikTok accounts on Cấu hình › Tài khoản affiliate. Empty: "Kết nối TikTok" says they are missing. To record the review demo, put the Sandbox's own key and secret here (and add the target TikTok account to the Sandbox), then restart api + worker. The Redirect URI registered on the app must be exactly `https://<web domain>/api/tiktok/oauth/callback` (fixed in `tiktok.REDIRECT_URI`) |
| `API_URL` | web: target of the `/api/*` rewrite, read by `next dev` and `next build` from the repo-root `.env`; in production the GitHub variable |

Only tests and E2E set these, to reach the local fake Claude, Pixabay, ElevenLabs, Gemini and Cloudflare Workers AI
([api/scripts/fake_services.py](../api/scripts/fake_services.py)): `ANTHROPIC_BASE_URL`,
`PIXABAY_API_URL`, `ELEVENLABS_API_URL`, `VIENEU_API_URL` (default `https://api.vieneu.io/api`; the fakes also empty `VIENEU_API_KEY`), `IMAGE_GEN_API_URL`, `IMAGE_GEN_CF_API_URL`, `FACEBOOK_API_URL`,
`SHOPEE_AFFILIATE_API_URL`, `TIKTOK_API_URL` (TikTok's Login Kit and Content Posting API; default `https://open.tiktokapis.com`), `SHOPEE_SHORT_LINK_URL` (where a pasted s.shopee.vn link is asked for its redirect; Shopee's keys are each member's, pasted on Cấu hình › Tài khoản affiliate, so there is no
Shopee key in `.env`; the fakes also
set `IMAGE_GEN_CF_ACCOUNT_ID=test-account` and a fake `IMAGE_GEN_CF_API_KEY`, so with `IMAGE_GEN_PROVIDER` unset Cloudflare is
the default; Gemini and Cloudflare tests set `IMAGE_GEN_PROVIDER` themselves). The Graph API version is the default in `config.facebook_api_url()`; change it there when Meta retires it. `JOB_TIMEOUT_SECONDS` (the job time limit) is lowered only in tests.

## Render machine

A member's own computer can render for the team, so the VPS only prepares jobs (narration, checks, files) and keeps
the web, the database and posting. Turn it on in **Cài đặt › Máy render** ("Render và cảnh động chạy trên máy
render"); while it is on, a render or a motion scene **waits until a machine takes it** (the owner's choice, no VPS
fallback): turn the switch off to have the VPS render again.

1. **Cài đặt › Máy render › Thêm máy**: name the computer and copy the command; the token is shown once.
2. On the computer (Windows), with FFmpeg (`winget install Gyan.FFmpeg`), Python 3.12 and, for motion scenes,
   Node 22 (`winget install OpenJS.NodeJS.LTS`), from the repository root:
   `powershell -ExecutionPolicy Bypass -File api\scripts\render-node.ps1 -Server https://<web-domain> -Token <token>`.
   The first run makes `api\.venv`, installs the api and the render core, and HyperFrames with GSAP in
   `%LOCALAPPDATA%\reels-hyperframes` (`-SkipMotion` leaves them out). It then waits for jobs; Ctrl+C stops it.
3. The machine shows "Đang chạy" on the page while it asks for jobs (every 5 s). A job it took and stopped answering
   for 10 minutes goes back to the queue; deleting the machine revokes its token and gives its job back.

The machine talks only to `/api/node/...` over HTTPS with its token (no cookie, no database, no storage): it
downloads the job's bundle, renders with its own FFmpeg (and HyperFrames), measures QC and uploads the MP4 (under
95 MB, Cloudflare's limit). The motion markup is checked before it is stored (`motion.check_markup`); on a Windows
machine the render's Chrome gets the proxy environment variables but not the Docker image's `--proxy-server`
wrapper, so that check is the main guard there.

## Operations

- **First account:** `python -m reels_api create-user` in `api/` (password typed hidden, twice);
  in production, run it in the Coolify terminal of the `api` container.
  After that, members add each other in the app.
- **Locked out** (forgotten password, everyone disabled): run the same command with an existing
  email; after confirmation it sets a new password, re-enables the account, and signs out its old
  sessions. Sessions need no secret: they are random tokens stored hashed in Postgres.
- **Storage growth:** each video is about 10–30 MB, which is about 1–3 GB/month at 3 videos/day.
  Deleting a video removes its folder for good; there is no other cleanup.
- **Worker:** its log (Coolify Logs of the worker app) shows `Worker lock acquired` once it takes
  jobs, one line per Claude call with token counts, and every job failure with its detail. A worker
  that starts while the database is unreachable waits and logs `Database unavailable`; once it holds
  the lock, losing the database or its lock connection makes it exit, and Coolify restarts it.
- **Production data on a dev machine:** `docker/pull-prod-db.sh <ssh-target> <postgres-container>`
  (bash; on Windows use Git Bash or WSL) dumps the production database over SSH (read only) into
  `data/prod-dumps/` and, after you type `reels` to confirm, replaces the local dev database
  `reels` with it; `--yes` skips the question. The container name is the end of the URL of Reels
  Studio's PostgreSQL resource in Coolify (`.../database/<container>`), not `coolify-db`: a dump
  without the `alembic_version` and `jobs` tables is deleted and the local database is left alone.
  Then run `alembic upgrade head` in `api/`. The copy has production's accounts and passwords;
  it cancels production's unfinished jobs; saved API keys and Fanpage tokens show as unreadable,
  because their key file stays in production's storage folder; video files and images are not
  copied. Only a person runs it, never an agent. The dump holds real member data: keep it on your
  machine.
- **Stuck or failed jobs** need no server action: jobs over the time limit are killed automatically
  (see [architecture.md](architecture.md#video-pipeline)),
  and members retry failed jobs from the video page. `/jobs` lists every job with its error and
  Claude call count.

Not yet defined: monitoring. Postgres backups use Coolify Scheduled Backups on the database
resource.
