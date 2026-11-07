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
- **Talk to the user in Vietnamese.** Code, comments, docs and commit messages are in English; the
  PR description fills [the PR template](.github/pull_request_template.md) in Vietnamese, so the
  team can judge it. Everything the app shows (labels, messages, errors) is in
  Vietnamese.
- **Bigger features** (new table, or a change across api + worker + web): write a short plan in the
  PR description: what changes, why, and how it was verified. No separate spec file is needed.
- **Done means:** lint and typecheck pass, tests for the changed behaviour exist and pass, and docs
  in `docs/` that describe the changed behaviour are updated in the same PR.
- **Bug fixes start with a failing test.** Write a test that reproduces the bug and watch it fail
  before fixing; the test stays as the regression guard.
- **Decisions are logged.** Read [docs/decisions.md](docs/decisions.md) before starting a new
  round of work. Never silently reverse a logged decision: if the work conflicts with one, stop
  and surface the conflict so the user can decide. A new decision made during the work is
  recorded there, dated, in the same PR.
- **Report in three parts** (in the PR description): what changed; which checks and tests were
  actually run, with their real results; and what is unfinished or turned up outside the task.
  Never claim a check passed that was not run.
- **Library docs:** use the Context7 MCP tools for library/API documentation and setup. Next.js here
  is v16; read [web/AGENTS.md](web/AGENTS.md) before writing web code.

## What to read

| Task | Read |
| --- | --- |
| Starting a new round of work | [docs/decisions.md](docs/decisions.md) |
| Any feature | [docs/project.md](docs/project.md), [docs/architecture.md](docs/architecture.md), [docs/patterns.md](docs/patterns.md) |
| Database, API, jobs, worker, render | [docs/architecture.md](docs/architecture.md) (Data Model, Video Pipeline, Render Core) |
| Prompt, script, knowledge base, safety rules | [docs/content.md](docs/content.md) |
| UI screens or the video template | [docs/ux-guidelines.md](docs/ux-guidelines.md) |
| Environment, Docker, deployment | [docs/deployment.md](docs/deployment.md) |
| Why an early feature was built a certain way | [docs/specs/](docs/specs/) (history, not kept up to date) |

Ideas, features and known bugs are [GitHub Issues](https://github.com/tuananh219ln/Reels-Studio/issues), opened from the forms in
[.github/ISSUE_TEMPLATE/](.github/ISSUE_TEMPLATE/) (Lỗi, Tính năng, Ý tưởng), written in Vietnamese.
A PR that ships one says `Closes #<number>` in its description.

## Layout

```text
api/      FastAPI + SQLAlchemy + Alembic; also the job worker (python -m reels_api worker)
worker/   reels_render: the FFmpeg render core and CLI, installed into api/
web/      Next.js 16 + Ant Design; proxies /api to the api
docs/     project documentation (shared by every agent)
```

## Commands

Python is 3.12 (`.python-version`, CI and the Docker images); Node is 22. Run from the repo root unless noted. One-time setup is in the README (it shows Windows paths; on
macOS/Linux use `.venv/bin/...`).

| What | Command |
| --- | --- |
| Python lint + format (api + worker, config in `ruff.toml`) | `api/.venv/bin/ruff check --fix api worker && api/.venv/bin/ruff format api worker` |
| api tests (need Postgres `reels_test` and FFmpeg) | `cd api && .venv/bin/python -m pytest -q` |
| worker tests | `cd worker && ../api/.venv/bin/python -m pytest -q` |
| web format, lint, typecheck (Prettier, ESLint, tsc) | `cd web && npm run format && npm run lint && npm run typecheck` |
| E2E (starts api, worker and fake services itself) | `cd web && npm run e2e` |
| New migration | `cd api && .venv/bin/alembic revision -m "..."`, then edit it |

Claude Code formats and lints every file it writes through
[.claude/hooks/format-lint.sh](.claude/hooks/format-lint.sh); other agents run the commands above
before finishing.

CI ([.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml)) runs all of the above on every PR;
a push to `main` deploys only after everything passes.

## Rules that are easy to break

- **Long work goes through the job queue.** Handlers enqueue and return; the worker does Claude
  calls, TTS and renders. See [docs/architecture.md](docs/architecture.md#video-pipeline).
- **Never edit a migration that is on `main`.** Add a new one.
- **No test switches in production code.** Tests reach Claude, Pixabay, ElevenLabs and Facebook
  only through their base-URL env vars pointing at `api/scripts/fake_services.py`.
- **Real APIs cost real money.** In development and tests, Claude, ElevenLabs and Facebook are
  reached only through the fake services; never retry a script or clone job in a loop, and never
  trigger jobs against production to test something.
- **Production is off-limits.** Never run commands in a Coolify terminal, connect to the
  production database, or run `create-user` against production. Production changes only through
  CI on merge to `main`; account recovery is the owner's job, by hand.
- **Prompt text is app data, the output format is code** ([docs/content.md](docs/content.md)).
- **Times are shown in Vietnam time** (`Asia/Ho_Chi_Minh`) whatever the browser's time zone.
- **Secrets stay in `.env`** (never committed; add new names to `.env.example`). Agents do not
  read `.env`. The one exception is what members paste on the Cài đặt pages (Fanpage tokens, LLM,
  stock-library and AI-image API keys): stored encrypted in the database, never sent back ([decisions](docs/decisions.md)). A new env var also updates the table in
  [docs/deployment.md](docs/deployment.md) in the same PR.
- **A person watches the render.** A change to the render core or the video template is done only
  when a person has watched a sample MP4 against [docs/ux-guidelines.md](docs/ux-guidelines.md)
  and said so in the PR; an agent cannot judge the visual result.
- **Never make a check pass by weakening it.** Do not delete tests or loosen their assertions,
  relax lint/format rules, skip CI steps, or add `noqa` / `eslint-disable` without a reason in the
  same line. Fix the code; if a check is truly wrong, say so in the PR and let a person decide.
- **Do not change** `.github/`, `ruff.toml`, `web/eslint.config.mjs`, migrations already on `main`,
  `AGENTS.md` or `.claude/` unless the task is about them: a mistake there is hard to undo or
  quietly turns a check off.

## Adding things (one place each)

- **API endpoints:** a new `api/src/reels_api/routes_<name>.py` exposing `router` is included
  automatically (`main.routers()`). Give it its own prefix.
- **A page behind the login:** a folder in `web/src/app/(app)/`. The login proxy and the E2E
  "redirects to login" test pick it up by themselves; add it to `NAV` in
  `web/src/components/AppShell.tsx` if it belongs in the menu.

## Git

- Branch from `main` (`feature/...`, `fix/...`, `chore/...`, `docs/...`); never commit to `main`.
- **Claim the work first.** Open a draft PR or take the issue before coding: one active branch
  per feature, and do not edit an area another open branch is already changing.
- Commits follow Conventional Commits: `feat(scope): ...`, `fix(scope): ...`.
- Keep PRs small. Merge `main` into your branch before opening the PR and again if it conflicts.
- **Green CI is the approval.** This is a team repo with no code owner: a PR may be merged, by its
  author or an agent asked to, once every CI check on it has passed and it is up to date with
  `main`. Never merge with a check failing or still running, never with `gh pr merge --admin` or
  any other bypass, and never make a check green by weakening it (see above).
- Never force-push, reset `--hard`, or push to `main` (Claude Code denies these in
  `.claude/settings.json`).
- An AI review runs on a PR only when someone with write access comments `/ai-review`
  ([claude-review.yml](.github/workflows/claude-review.yml)); each run costs API tokens. Agents
  never post that comment themselves. Answer or fix each point it raises.
- A comment mentioning `@claude` on an issue or PR, from someone with write access, gets a read-only
  answer about the project ([claude-ask.yml](.github/workflows/claude-ask.yml)); each run costs
  API tokens. Agents never post such a comment themselves.
