# Reels Studio: rules for every AI agent

Internal web app that turns a topic into a ready-to-post 9:16 short video (Claude script, scene
images, FFmpeg render) for Reels, TikTok and Shorts, used by a team of about five.

This file is the single source of rules for every agent (Claude Code, Codex, Cursor, Copilot,
Gemini, ...). `CLAUDE.md` only imports it. Project documentation lives in [docs/](docs/); there are
no agent-specific copies, so edit the file here and in `docs/`, never a generated one.

## How to work

- **Lean.** Do the task directly: read only the docs and code the task needs, change it, verify
  with the commands below, report. No subagents, no multi-agent reviews, no interview or spec
  rituals. Ask the user only when a decision is genuinely theirs.
- **Talk to the user in Vietnamese.** Code, comments, docs, commit messages and PR text are in
  English. Everything the app shows (labels, messages, errors) is in Vietnamese.
- **Bigger features** (new table, or a change across api + worker + web): write a short plan in the
  PR description: what changes, why, and how it was verified. No separate spec file is needed.
- **Done means:** lint and typecheck pass, tests for the changed behaviour exist and pass, and docs
  in `docs/` that describe the changed behaviour are updated in the same PR.
- **Library docs:** use the Context7 MCP tools for library/API documentation and setup. Next.js here
  is v16; read [web/AGENTS.md](web/AGENTS.md) before writing web code.

## What to read

| Task | Read |
| --- | --- |
| Any feature | [docs/project.md](docs/project.md), [docs/architecture.md](docs/architecture.md), [docs/patterns.md](docs/patterns.md) |
| Database, API, jobs, worker, render | [docs/architecture.md](docs/architecture.md) (Data Model, Video Pipeline, Render Core) |
| Prompt, script, knowledge base, safety rules | [docs/content.md](docs/content.md) |
| UI screens or the video template | [docs/ux-guidelines.md](docs/ux-guidelines.md) |
| Environment, Docker, deployment | [docs/deployment.md](docs/deployment.md) |
| Why an early feature was built a certain way | [docs/specs/](docs/specs/) (history, not kept up to date) |

Ideas and known bugs go in [backlog.md](backlog.md) (in Vietnamese, with the date added). Remove an
item when it ships.

## Layout

```text
api/      FastAPI + SQLAlchemy + Alembic; also the job worker (python -m reels_api worker)
worker/   reels_render: the FFmpeg render core and CLI, installed into api/
web/      Next.js 16 + Ant Design; proxies /api to the api
docs/     project documentation (shared by every agent)
```

## Commands

Run from the repo root unless noted. One-time setup is in the README (it shows Windows paths; on
macOS/Linux use `.venv/bin/...`).

| What | Command |
| --- | --- |
| Python lint + format (api + worker, config in `ruff.toml`) | `api/.venv/bin/ruff check --fix api worker && api/.venv/bin/ruff format api worker` |
| api tests (need Postgres `reels_test` and FFmpeg) | `cd api && .venv/bin/python -m pytest -q` |
| worker tests | `cd worker && ../api/.venv/bin/python -m pytest -q` |
| web format, lint, typecheck (Prettier, ESLint, tsc) | `cd web && npm run format && npm run lint && npm run typecheck` |
| E2E (starts api, worker and fake services itself) | `cd web && npm run e2e` |
| New migration | `cd api && .venv/bin/alembic revision -m "..."`, then edit it |

CI ([.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml)) runs all of the above on every PR;
a push to `main` deploys only after everything passes.

## Rules that are easy to break

- **Long work goes through the job queue.** Handlers enqueue and return; the worker does Claude
  calls, TTS and renders. See [docs/architecture.md](docs/architecture.md#video-pipeline).
- **Never edit a migration that is on `main`.** Add a new one.
- **No test switches in production code.** Tests reach Claude, Pixabay, ElevenLabs and Facebook
  only through their base-URL env vars pointing at `api/scripts/fake_services.py`.
- **Prompt text is app data, the output format is code** ([docs/content.md](docs/content.md)).
- **Times are shown in Vietnam time** (`Asia/Ho_Chi_Minh`) whatever the browser's time zone.
- **Secrets stay in `.env`** (never committed; add new names to `.env.example`).

## Adding things (one place each)

- **API endpoints:** a new `api/src/reels_api/routes_<name>.py` exposing `router` is included
  automatically (`main.routers()`). Give it its own prefix.
- **A page behind the login:** a folder in `web/src/app/(app)/`. The login proxy and the E2E
  "redirects to login" test pick it up by themselves; add it to `NAV` in
  `web/src/components/AppShell.tsx` if it belongs in the menu.

## Git

- Branch from `main` (`feature/...`, `fix/...`, `chore/...`, `docs/...`); never commit to `main`.
- Commits follow Conventional Commits: `feat(scope): ...`, `fix(scope): ...`.
- Keep PRs small. Merge `main` into your branch before opening the PR and again if it conflicts.
