# Deployment & Operations

## Current State

Development runs locally (below). Production is defined but not yet switched on: it starts once the
owner completes the one-time setup in the README ("Triển khai (CI/CD)").

**Development host:** a Windows 10 Pro machine (Intel i7-8700). The render core runs natively,
without Docker: Python 3.12 and FFmpeg are installed with winget (`Python.Python.3.12`,
`Gyan.FFmpeg`), and the package is installed into `worker/.venv`. If `python` opens the Microsoft
Store, disable the alias under "App execution aliases" or call the installed interpreter
directly.

Postgres runs in Docker (Docker Desktop with WSL2) via `docker compose up -d postgres`; `api` and
`web` run natively in development. On the first start of an empty volume,
`docker/postgres-init/` creates `reels_test` (pytest) and `reels_e2e` (Playwright) next to the dev
database. Use `127.0.0.1` rather than `localhost` in local URLs: on this host `localhost` tries IPv6
first and adds a 5-second delay. The setup commands are in the README.

**Render budget:** rendering must take no longer than 2× the video length on this host.

## Production

| Part | Where | How it is built |
|---|---|---|
| `api` | Coolify application, Dockerfile build pack, base directory `/api` | Coolify builds [api/Dockerfile](../../../../api/Dockerfile) from git |
| `postgres` | Coolify standalone PostgreSQL 17, database `reels`, not public | Not redeployed by CI; Coolify Scheduled Backups |
| `web` | Cloudflare Workers, worker `reels-studio-web` ([web/wrangler.jsonc](../../../../web/wrangler.jsonc)) | `@opennextjs/cloudflare` in GitHub Actions |

- **Why Workers, not Pages:** the web app needs a server runtime for `proxy.ts` and the `/api/*`
  rewrite. Cloudflare runs full Next.js through OpenNext on Workers; the old Pages adapter is
  deprecated. Next.js 16's `proxy.ts` is Node middleware, which OpenNext Cloudflare supports only
  as experimental: the build prints a warning. Keep `proxy.ts` to a cookie check.
- **One origin is kept:** the worker forwards `/api/*` to `API_URL` (the Coolify api domain),
  baked in at build time. The browser only talks to the web domain, so the session cookie stays
  first-party. The api's own domain is public too; the `Origin` check still guards it.
- **Delivery:** [.github/workflows/ci-cd.yml](../../../../.github/workflows/ci-cd.yml). Every PR
  runs api pytest (with the Docker image build), worker pytest with FFmpeg, web typecheck + E2E +
  Cloudflare build. A push to `main` that passes all of them deploys: Coolify deploy webhook first,
  waiting for Coolify to report `finished`, then `npm run deploy` in `web/`. Coolify auto-deploy
  must stay off, or a push deploys before the tests pass.
- **Database URL:** the api's `DATABASE_URL` is the Postgres internal URL Coolify shows
  (`postgres://…`); `config.database_url()` rewrites a driverless `postgres://`/`postgresql://`
  scheme to `postgresql+psycopg://`.
- **Migrations** run in the api container on every start (`alembic upgrade head`), before uvicorn.
  Write migrations so the previous api version keeps working until the web deploy finishes.
- **GitHub environment `production`:** secrets `COOLIFY_WEBHOOK`, `COOLIFY_TOKEN`,
  `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`; variable `API_URL`.
- **Rollback:** api — redeploy an earlier deployment in Coolify; web — `npx wrangler rollback` in
  `web/` or the Workers dashboard. A rollback does not revert migrations.

**Planned runtime:** `worker` and `redis` become further Coolify resources next to the api, plus
the storage volume (see [architecture.md](architecture.md#components)), when they are built.

## Environment Variables

**See:** [.env.example](../../../../.env.example). It lists only the variables in use so far; the
scaffold adds the rest. The render core reads `.env` at the repo root; a real environment variable
wins, even when set to an empty string.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API |
| `CLAUDE_MODEL` | Model override; the default is `claude-sonnet-5-5` |
| `PIXABAY_API_KEY` | Stock image search in the render core (in use) |
| `TTS_PROVIDER` | `edge` or `azure` |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | Needed only when `TTS_PROVIDER=azure` |
| `DATABASE_URL` | api: dev database; in production the Coolify Postgres internal URL (in use) |
| `TEST_DATABASE_URL` | api: pytest database `reels_test` (in use) |
| `ALLOWED_ORIGINS` | api: comma-separated origins allowed to change data; the default is `http://localhost:3000`; in production the web domain (in use) |
| `COOKIE_SECURE` | api: `true` adds the Secure flag to the session cookie; set on the Coolify application, empty on localhost (in use) |
| `API_URL` | web: target of the `/api/*` rewrite, read by `next dev` and `next build` from the repo-root `.env`; in production the GitHub variable (in use) |
| `REDIS_URL` | Queue connection |
| `STORAGE_DIR` | Root of the media storage volume |
| `RENDER_CONCURRENCY` | Maximum parallel render jobs; the default is 1 |

Except those marked "in use", these names are planned and will be finalized at scaffold time. After that, keep this table in
sync with `.env.example`.

## Operations

- **First account:** `python -m reels_api create-user` in `api/` (password typed hidden, twice);
  in production, run it in the Coolify terminal of the `api` container.
  After that, members add each other in the app.
- **Locked out** (forgotten password, everyone disabled): run the same command with an existing
  email; after confirmation it sets a new password, re-enables the account, and signs out its old
  sessions. Sessions need no secret: they are random tokens stored hashed in Postgres.
- **Storage growth:** each video is about 10–30 MB, which is about 1–3 GB/month at 3 videos/day.
  There is no cleanup in the MVP.

Not yet defined: monitoring. Postgres backups use Coolify Scheduled Backups on the database
resource.
