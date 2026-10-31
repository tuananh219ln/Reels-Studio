# Code Research: web-app-auth

Date: 2026-10-29. Scope: first web app of Reels Studio — Next.js (TypeScript) `web`, FastAPI `api`,
Postgres; email/password login without self-signup, first account by CLI, member management with
temporary passwords and forced change, 30-day sliding httpOnly cookie session, app shell + empty
Video list, Members, Change password, and "Sắp có" placeholders.

Sources: repo files (cited by path), host checks run in this session, Context7 docs (cited by
library ID), and PyPI/npm "latest version" queries run 2026-10-29.

---

## 1. Entry Points

There is **no web or API code** yet. `git ls-files` shows only:

- `worker/` — the Python package `reels_render` (render core + CLI). It is the only application code.
- Agent/skill docs (`.claude/`, `.codex/` generated), `.github/workflows/online-pipeline-*.yml`,
  `.githooks/pre-commit`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `backlog.md`, `.env.example`,
  `.gitignore`, `samples/`, `work/`.

So the feature defines every entry point. Existing CLI entry point to mirror for the
"create first account" command:

- `worker/src/reels_render/__main__.py` + `worker/src/reels_render/cli.py` — `python -m reels_render`;
  `def main(argv: list[str] | None = None) -> int` with `argparse`, Vietnamese help/errors, and
  `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` because piped output on
  Windows uses the ANSI code page and cannot encode Vietnamese (cli.py top of `main`).

Planned surfaces (from `.claude/skills/project-knowledge/references/architecture.md` → Components):
`web` "Next.js UI. Calls the API only."; `api` "FastAPI app. Handles auth, CRUD …". Screens listed
in `ux-guidelines.md` → Screens (MVP): Login, Video list, Script/scene editor, Knowledge Base,
Music library, Job log. Members and Change-password screens are not in ux-guidelines.md yet
(they come from this feature's interview).

Approved visual design: prototype artifact `https://claude.ai/artifact/9rHaJJFHQMgVcnEXLvQXcB`
(screens 1 Đăng nhập, 2 Video, 7 Thành viên; shared shell). Style tokens recorded in
`work/web-app-auth/logs/userspec/interview.yml` → `feature_description`: white left menu, selected
item teal `#0F3B4C`, green "RS" logo badge, page background `#F7F7F7`, white cards with `#EDEDED`
border, header avatar + "Đăng xuất".

## 2. Data Layer

No database, models, or migrations exist. Documented model
(`.claude/skills/project-knowledge/references/architecture.md` → Data Model):

| Entity | Documented contents |
|---|---|
| User | email, password hash |
| Video | topic, titles, caption, hashtags, … (not in this feature beyond an empty list) |

- "The migration tool will be chosen at scaffold time." (architecture.md → Data Model).
- Sensitive Data: "Passwords are stored hashed." "The only personal data is team members' emails."
  API keys only in env vars, never in DB.

Fields this feature's behavior implies (not documented yet; facts derived from the interview):

- `User`: needs a flag for "must change password" (temp password login forces change), plus
  created/updated timestamps. No role field (team 2–5, no roles — interview `target_users`).
- Session storage: 30-day sliding session + "remove member" + "reset password" means sessions must
  be revocable server-side. `deployment.md` lists a planned `SESSION_SECRET` ("Auth session
  signing"); with a DB-stored opaque token (stored hashed) the secret is not strictly needed, with a
  signed stateless cookie removal/reset cannot revoke existing sessions without a per-user
  version/counter. Open choice — interview gap "Session storage".
- Email uniqueness: Postgres unique index on a normalized (lowercased) email, or `citext`.

`Video` table: the Video list screen is empty in this feature; interview gap "Video list: empty
state only, or create-video stub?" is still open, so whether a `video` table/migration lands now is
undecided.

## 3. Similar Features

No auth, web, or DB code exists anywhere in the repo or its history (`git log` shows only
render-core, stock-image-search, and docs commits). Reusable patterns from `worker/`:

- **Package layout:** `worker/pyproject.toml` — setuptools, `src/` layout
  (`[tool.setuptools.packages.find] where = ["src"]`), `requires-python = ">=3.12"`,
  `[project.optional-dependencies] dev = ["pytest>=8"]`, `[tool.pytest.ini_options] testpaths =
  ["tests"]`. Per-component venv at `worker/.venv` (memory file `dev-tool-paths.md`). An `api/` with
  its own `pyproject.toml`, `src/<pkg>/`, `tests/`, `.venv` matches this.
- **Env reading:** `worker/src/reels_render/env.py` — `read_env(name: str) -> str`; real env var wins
  even if empty; `.env` at repo root located by `Path(__file__).resolve().parents[3] / ".env"`;
  reads with `utf-8-sig` (PowerShell BOM), supports `export`, quotes, comments. Tested in
  `worker/tests/test_env.py`. The api could reuse the same rules (or pydantic-settings with
  `env_file` pointing at the repo-root `.env`; note pydantic-settings precedence also lets real env
  vars win).
- **Typed errors with Vietnamese user-facing messages:** `worker/src/reels_render/errors.py`
  (`class RenderError(Exception)` "the message is Vietnamese and user-facing"). Same convention fits
  API error responses shown in the Vietnamese UI.
- **Vietnamese CLI UX:** `cli.py` argparse with Vietnamese descriptions; `_warn()` prints
  "Cảnh báo: …" to stderr.

Repo-root leftovers from an earlier Remotion prototype (untracked/ignored, not in git):
`node_modules/` (Remotion deps, ignored by `node_modules/` rule), `out/` (ignored), empty
`knowledge/`, `public/music`, `public/photos` (untracked, empty). No root `package.json`.

## 4. Integration Points

- **Repo-root `.env`** (ignored by `.gitignore` `.env`, `.env.*`, with `!.env.example`). Current keys:
  `PIXABAY_API_KEY`, `PEXELS_API_KEY` (the latter unused/undocumented). `.env.example` contains only
  `PIXABAY_API_KEY=`. `deployment.md` → Environment Variables: planned `DATABASE_URL`, `REDIS_URL`,
  `SESSION_SECRET`, `STORAGE_DIR`, …; "the scaffold adds the rest. … keep this table in sync with
  `.env.example`."
- **Docs to update at finalize:** `deployment.md` (env vars table, dev host state, "First account:
  created by a CLI command"), `architecture.md` (Data Model User fields, migration tool choice,
  "Status: only the render core … is built"), `patterns.md` (testing for api/web, quality gates),
  `ux-guidelines.md` (Members/Change-password screens), `README.md` (project structure tree),
  `SKILL.md` intro ("Only the render core and its CLI exist").
- **Pre-commit hook** `.githooks/pre-commit`: when `.claude/**` is staged it runs
  `~/.claude/scripts/sync-to-codex.sh` and stages `AGENTS.md` + `.codex/`; skips with a warning if
  the script is missing. Doc changes in `.claude/` trigger it.
- **Worker:** no runtime integration in this feature. Future worker will share `DATABASE_URL` and
  the User/Video tables; a shared DB models package location (api-owned vs shared) is not decided.
- **Web ↔ API transport:** see section 9 (rewrites vs CORS). `architecture.md`: `web` "Calls the API
  only."

## 5. Existing Tests

- Framework: pytest 9.2.0 (installed in `worker/.venv`), run from `worker/` (`patterns.md` →
  Testing). Tests import the installed editable package.
- Fixture pattern: `worker/tests/conftest.py` — autouse `offline(tmp_path, monkeypatch)` that strips
  `PIXABAY_API_KEY`, redirects `env.DOTENV_PATH` to a missing file, and fails on any network call;
  helper fakes (`class FakePixabay`) instead of mocking libraries. Skip markers with Vietnamese
  reasons: `needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe không có trên PATH")`.
- Representative signatures:
  - `def test_real_environment_variable_wins_over_dotenv(tmp_path, monkeypatch)` (`test_env.py`)
  - `def test_dotenv_is_read_from_the_repo_root()` (`test_env.py`)
- No JS/TS tests, no API tests, no DB tests. `patterns.md`: "Backend: pytest." "Frontend: tests cover
  the main flows only." Quality gates in CI: "planned and not yet configured" — no lint/test workflow
  exists (`.github/workflows/` has only online-pipeline workflows, which install Claude Code, not
  project deps).
- The api test suite needs the same isolation idea as `offline`: never read the developer's real
  `.env`/`DATABASE_URL` by accident (e.g. require a separate `TEST_DATABASE_URL`).

## 6. Shared Utilities

- `worker/src/reels_render/env.py` — `read_env`, `_read_dotenv`, `DOTENV_PATH` (see section 3).
- `worker/src/reels_render/errors.py` — `RenderError` hierarchy (pattern only).
- No shared JS utilities, no UI component library, no design tokens file. UI component approach
  (Ant Design vs hand-made) is an open interview gap (`ui_ux_requirements`). The MKT-Tools reference
  style is an admin layout; `antd` latest is 6.6.8 (npm, 2026-10-29) if chosen.

## 7. Potential Problems

**Security**

- **Session fixation / revocation:** removing a member or resetting their password must invalidate
  their existing sessions; a stateless signed cookie cannot do that alone (section 2).
- **CSRF:** cookie auth means any state-changing endpoint (login, logout, create/reset/remove member,
  change password) is CSRF-relevant. `SameSite=Lax` cookies are not sent on cross-site POST/PUT/DELETE
  (FastAPI `set_cookie` default `samesite="lax"`, Context7 `/websites/fastapi_tiangolo`). With web
  and api served same-origin via Next.js rewrites, adding an `Origin`/`Sec-Fetch-Site` check or
  requiring `Content-Type: application/json` on mutations closes the remaining gaps (subdomain
  siblings are "same-site"). Next.js Server Actions get Origin-vs-Host checking built in (Context7
  `/vercel/next.js/v16.2.9`, data-security guide); a FastAPI endpoint reached through a rewrite does
  not.
- **Login brute force / user enumeration:** no rate limiting exists anywhere. Same error text for
  unknown email vs wrong password; constant-ish timing (verify against a dummy hash when the user is
  missing).
- **Temp password handling:** temp passwords must be shown once to the creating member and never
  logged; stored only as a hash. How the temp password is delivered is an open interview gap.
- **Self-removal / last member:** removing yourself or the last account leaves the app unusable
  without the CLI — open interview gap ("Can a member remove themselves / last member").
- **Email normalization:** case/whitespace differences can create duplicate accounts unless
  normalized + unique.
- **Cookie `Secure` flag:** dev runs on `http://localhost`; production must set `Secure`. Needs a
  config switch (e.g. derived from an env var), otherwise either dev login breaks or prod cookies
  are insecure.
- **Proxy redirect only is not authorization:** Next.js docs call proxy checks "optimistic"; the API
  must enforce auth on every endpoint, and the forced-password-change state must be enforced by the
  API too (not only by a UI redirect).

**Platform / tooling**

- `python` on this host opens the Microsoft Store stub; use
  `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (3.12.10 verified) — `deployment.md` and
  memory `dev-tool-paths.md`.
- Windows console encoding for the CLI (see section 1, `cli.py`) — the create-first-account command
  prints Vietnamese text and reads a password (prompting via `getpass` works in a terminal; it must
  not hang when stdin is not a TTY, mirroring `cli.py`'s `sys.stdin.isatty()` check).
- Repo-root `node_modules/` (Remotion leftovers) sits above a future `web/`: Node module resolution
  walks up directories, so a package missing from `web/package.json` could silently resolve from
  the root `node_modules/`. Next.js may also infer the workspace root from lockfiles; there is no
  root lockfile today (only `node_modules/.package-lock.json`).
- Path with a space (`C:\Users\Young Sheldon\...`): scripts and docker volume/bind paths must quote.
- `.gitignore` has `out/`, `build/`, `dist/`, `.next/`, `data/` rules; a Postgres bind-mount under
  `data/` would be ignored (good), but any source folder named `data/`, `build/`, or `out/` inside
  `web/` or `api/` would also be ignored silently.

## 8. Constraints & Infrastructure

**Host facts (checked 2026-10-29 in this session)**

| Item | State |
|---|---|
| OS | Windows 10 Pro 22H2 (10.0.19045) |
| Python | 3.12.10 at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`; no `uv`, `pipx` |
| Node / npm | v24.22.1 / 11.19.1; no `pnpm`, `yarn` |
| Docker | not installed (`docker` not on PATH, no `C:\Program Files\Docker`) |
| WSL | `wsl.exe --status` prints legacy usage text → WSL2 not installed/enabled |
| Virtualization | `VirtualizationFirmwareEnabled = True`, `HypervisorPresent = False` |
| Postgres | no local install (`psql` absent, no `C:\Program Files\PostgreSQL`) |
| Ports 3000, 5432, 8000, 8080 | no listeners |
| gh | `/c/Program Files/GitHub CLI/gh.exe`, logged in (memory file) |

- **Docker Desktop on Win10 Pro:** needs the WSL2 backend (or Hyper-V, available on Pro).
  Firmware virtualization is on, but no hypervisor is running, so installing WSL2
  (`wsl --install`, admin + reboot) or enabling Hyper-V is a prerequisite. Until Docker works there is
  no Postgres at all on this host — the api cannot start and DB-backed tests cannot run. Fallback
  options (not decided): native Postgres via winget (`PostgreSQL.PostgreSQL.17`), or tests that skip
  without a DB (mirrors `needs_ffmpeg`).
- **Port 5432** is free now; a later native Postgres install would collide with the compose
  service — map compose to a non-default host port or document it.
- **Repo layout:** components named `web`, `api`, `worker`, `postgres`, `redis`
  (`architecture.md` → Components). `worker/` sits at repo root, so `web/` and `api/` at repo root
  follow the same convention. Compose file location undecided (repo root `docker-compose.yml` /
  `compose.yaml` fits "single compose for dev + VPS" in `deployment.md`).
- **Planned runtime:** Docker Compose for `web`, `api`, `worker`, `postgres`, `redis` + storage volume;
  same setup on a single VPS (`deployment.md` → Current State). This feature's compose covers web,
  api, postgres only (interview). Production host, domain, TLS, backups are "Not yet defined".
- **Env vars:** names other than `PIXABAY_API_KEY` are "planned and will be finalized at scaffold
  time" (`deployment.md`). New ones likely: `DATABASE_URL`, possibly `SESSION_SECRET`, an API base
  URL for the Next.js rewrite, a cookie-secure switch, test DB URL.
- **No CI** for lint/tests; online-pipeline workflows run on `ubuntu-latest` and only install
  `@anthropic-ai/claude-code`.
- **UI language:** Vietnamese only, no i18n (`ux-guidelines.md`). `<html lang="vi">`; Vietnamese
  diacritics need a font with Vietnamese subset (Be Vietnam Pro is already the video font; via
  `next/font/google` it has a `vietnamese` subset).
- **Git flow:** feature branch → PR into `main` (`patterns.md`); current branch
  `userspec/web-app-auth`.

## 9. External Libraries

Latest versions (PyPI `pip index versions`, npm `npm view`, 2026-10-29):

| Package | Latest |
|---|---|
| fastapi | 0.162.0 |
| uvicorn | 0.54.0 |
| sqlalchemy | 2.1.6 |
| alembic | 1.20.1 |
| psycopg | 3.3.6 |
| sqlmodel | 0.0.48 |
| pwdlib | 0.3.1 |
| argon2-cffi | 25.1.0 |
| pydantic-settings | 2.16.2 |
| httpx | 0.28.1 |
| pytest | 9.2.0 |
| testcontainers | 4.15.0 |
| next | 16.4.3 |
| react | 19.3.1 |
| typescript | 7.0.2 |
| vitest | 5.0.5 |
| @playwright/test | 1.64.1 |
| @testing-library/react | 16.3.3 |
| antd | 6.6.8 |

### FastAPI (Context7 `/websites/fastapi_tiangolo`)

- `Response.set_cookie(key, value="", max_age=None, expires=None, path="/", domain=None,
  secure=False, httponly=False, samesite="lax", partitioned=False)`; `partitioned` needs Python
  3.14+. Sliding session = re-issue `Set-Cookie` with a fresh `max_age` (30 days = 2592000 s) when the
  session is extended.
- Current-user pattern: `async def get_current_user(...)` used as
  `Annotated[User, Depends(get_current_user)]`. For cookies, read via `Cookie()` parameter or
  `Request.cookies` instead of `OAuth2PasswordBearer`.
- Tests: `TestClient(app)` (httpx-based) keeps cookies across requests in the client; use
  `with TestClient(app) as client:` to run lifespan; `app.dependency_overrides[get_db] = override`
  swaps the DB session dependency.
- CORS: only needed if the browser calls the API on a different origin; cookies cross-origin need
  `allow_credentials=True` with explicit origins, and `SameSite=None; Secure` if cross-site.

### Next.js 16 (Context7 `/vercel/next.js/v16.2.9`)

- Requires Node.js >= 20.9.0 and TypeScript >= 5.1 (upgrade guide v16). Host Node v24 satisfies.
- `middleware.ts` is renamed **`proxy.ts`**, exported function `proxy`; proxy runtime is `nodejs`
  only. Auth guide: proxy does *optimistic* cookie checks and redirects (`NextResponse.redirect(new
  URL('/login', req.nextUrl))`), with `matcher` excluding `api|_next/static|_next/image`; real
  checks belong in a server-only Data Access Layer (`verifySession` using `cookies()` from
  `next/headers`, memoized with React `cache`).
- Proxying to a backend: `rewrites()` in `next.config.ts`
  (`{ source: '/api/:path*', destination: 'https://backend/:path*' }`, CRA-migration and
  backend-for-frontend guides). Keeps browser→API traffic same-origin, so cookies are first-party,
  `SameSite=Lax` works, and no CORS is needed. Server Components calling the API directly (server
  side `fetch`) must forward the incoming cookie header themselves.
- `output: 'standalone'` for a minimal Docker image (output config docs).
- Server Actions: CSRF-protected by POST + SameSite + Origin/Host comparison;
  `experimental.serverActions.allowedOrigins` for reverse proxies (data-security guide).
- Testing: "Vitest currently does not support `async` Server Components … recommended to use
  End-to-End (E2E) tests for `async` components" (Vitest guide). Playwright is the documented E2E
  option.
- Not verified in docs this session: rewrite destinations are resolved at `next build` time, so an
  env-driven API URL must be present during the Docker build, not only at runtime.

### Password hashing — pwdlib (Context7 `/websites/frankie567_github_io_pwdlib`)

- Install `pip install 'pwdlib[argon2]'` (pulls argon2-cffi, which has Windows wheels).
- `PasswordHash.recommended()` → Argon2 with default parameters; `.hash(password) -> str`;
  `.verify(password, hash) -> bool` (raises `UnknownHashError` on unrecognized hash);
  `.verify_and_update(password, hash) -> tuple[bool, str | None]` rehashes when algorithm/params
  change. FastAPI's own security tutorial uses pwdlib (passlib is unmaintained). Direct
  `argon2-cffi` (`PasswordHasher().hash/verify/check_needs_rehash`) is the lower-level alternative.

### SQLAlchemy 2.x (Context7 `/websites/sqlalchemy_en_20_core`, `/websites/sqlalchemy_en_20_orm`)

- URL form `dialect+driver://user:password@host:port/dbname`; psycopg 3 driver name is `psycopg`
  (`postgresql+psycopg://...`); default `postgresql://` maps to psycopg2. Special characters in
  passwords must be URL-encoded.
- Test isolation recipe: open a `Connection`, `begin()` an outer transaction, bind
  `Session(bind=connection, join_transaction_mode="create_savepoint")`; app code may `commit()`, and
  teardown rolls everything back. Relies on SAVEPOINT support — reliable on Postgres; the docs warn
  SQLite's driver mishandles SAVEPOINTs without workarounds.
- Alembic docs already link SQLAlchemy 2.1 pages; latest release is 2.1.6.
- SQLModel (0.0.48) is still pre-1.0; plain SQLAlchemy 2 `DeclarativeBase` + `Mapped`/`mapped_column`
  is the stable alternative.

### Alembic (Context7 `/websites/alembic_sqlalchemy_en`)

- Autogenerate needs `target_metadata = Base.metadata` in `env.py`.
- Recommended `MetaData(naming_convention={"ix": ..., "uq": ..., "ck": ..., "fk": ..., "pk": ...})`
  on the declarative `Base` so constraints get deterministic names.
- `sqlalchemy.url` can be set from `DATABASE_URL` inside `env.py` instead of `alembic.ini`, which
  keeps credentials out of committed files.

### Test DB options (facts)

- Postgres test DB: matches prod semantics (unique indexes, `citext`, timestamps with time zone,
  savepoints). Needs Postgres running — on this host only after Docker/WSL2 or a native install.
- SQLite: no server needed, but differs in types/constraints and savepoint handling (SQLAlchemy
  docs above); Postgres-specific DDL (e.g. `citext`) would not run.
- testcontainers (4.15.0) starts a throwaway Postgres container per session — also needs Docker.
