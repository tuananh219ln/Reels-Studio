# Deployment & Operations

## Current State

The project runs locally only. There is no production server, domain, or CI/CD deployment yet.
The owner will deploy later.

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

**Planned runtime:** Docker Compose will run `web`, `api`, `worker`, `postgres`, and `redis`,
plus the storage volume (see [architecture.md](architecture.md#components)). The same compose setup is the planned
production setup on a single VPS.

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
| `DATABASE_URL` | api: dev database (in use) |
| `TEST_DATABASE_URL` | api: pytest database `reels_test` (in use) |
| `ALLOWED_ORIGINS` | api: comma-separated origins allowed to change data; the default is `http://localhost:3000` (in use) |
| `API_URL` | web: target of the `/api/*` rewrite, read by `next dev` and `next build` from the repo-root `.env` (in use) |
| `REDIS_URL` | Queue connection |
| `STORAGE_DIR` | Root of the media storage volume |
| `RENDER_CONCURRENCY` | Maximum parallel render jobs; the default is 1 |

Except those marked "in use", these names are planned and will be finalized at scaffold time. After that, keep this table in
sync with `.env.example`.

## Operations

- **First account:** `python -m reels_api create-user` in `api/` (password typed hidden, twice).
  After that, members add each other in the app.
- **Locked out** (forgotten password, everyone disabled): run the same command with an existing
  email; after confirmation it sets a new password, re-enables the account, and signs out its old
  sessions. Sessions need no secret: they are random tokens stored hashed in Postgres.
- **Storage growth:** each video is about 10–30 MB, which is about 1–3 GB/month at 3 videos/day.
  There is no cleanup in the MVP.

Not yet defined: production host, delivery path, rollback, monitoring, and backups. Fill these in
when the VPS deployment is specified.
