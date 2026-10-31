# Decision Log

Settled product and technical decisions, each with a short reason, so every person and every
coding agent working on this repo knows why things are the way they are.

How to use: add a new decision as a new entry at the top, with its date. Never edit an old entry.
If a new decision replaces an old one, say so in the new entry. Agents read this file before
starting a new round of work and never silently reverse a logged decision (see
[AGENTS.md](../AGENTS.md)).

The entries dated 2026-10-31 were recorded retroactively: the decisions were already in effect
in the MVP and described across `docs/`; this log gathers them in one place.

## 2026-10-31 — Narration reads the on-screen text, then the voice text

The spoken text is joined when the render runs rather than copied into the voice text, so choosing
another title or editing a scene's text is always what gets read. An empty voice text still means a
silent scene. Claude's voice texts got shorter and no longer repeat the screen, and the 120-word
budget now counts both, to keep a video under 48 seconds.

## 2026-10-31 — Decisions are logged in the repo

Settled decisions are recorded in this file, in the repo, because agents and team members can
only read the repo — not anyone's chat history or memory. The rules for every agent live in one
place, `AGENTS.md`; `CLAUDE.md` only imports it.

## 2026-10-31 — Own repository, not a fork of MoneyPrinterTurbo

The pipeline stages follow MoneyPrinterTurbo (MIT, attribution kept in adapted files), but this
is its own codebase: MoneyPrinterTurbo has no auth, no database and no scene model, carries many
unused providers and OAuth flows, and uses stock video clips instead of member photos.

## 2026-10-31 — The job queue is the Postgres `jobs` table, not Redis

At 1–3 videos a day a separate queue service is not worth running. Long work (Claude calls, TTS,
renders, Facebook posting) never runs in the API process; the worker runs it.

## 2026-10-31 — One worker only; a dead worker's job is never re-run automatically

The worker holds a Postgres advisory lock for its whole life, so exactly one worker takes jobs.
A job still marked running when a worker starts belonged to a worker that died: it becomes
failed ("Worker khởi động lại giữa chừng") and a member retries it by hand. Auto-rerunning could
spend Claude or ElevenLabs credit without anyone deciding to.

## 2026-10-31 — Rendering is a native FFmpeg filter graph; no MoviePy, no Remotion

MoviePy composites frames in Python and is the speed bottleneck. Remotion needs a paid Company
License for teams of four or more. Pillow pre-renders text boxes as transparent PNGs and FFmpeg
does the compositing (`zoompan` for Ken Burns motion, `overlay` for text).

## 2026-10-31 — Server renders use member-uploaded scene photos only

Every scene photo or clip is uploaded by a member while editing, so the render uses exactly what
the preview showed; a scene without one blocks the render. Stock search (Pixabay) exists only in
the render core's CLI path — the web UI no longer offers it and jobs never pick photos. No source
or license info is stored for stock photos (owner's decision).

## 2026-10-31 — Narration is ElevenLabs "Adam" on `eleven_v3`, stored per scene and reused

`eleven_multilingual_v2` does not speak Vietnamese, so the model is `eleven_v3` with
`language_code: vi`. Narration is paid per character, so each scene's MP3 is stored and re-made
only when its text, voice or model changes.

## 2026-10-31 — Fanpages are connected by pasting a Page token; there is no OAuth flow

A user or system user token is swapped for each Page's own token through `/me/accounts`, and that
token is what is kept — stored encrypted with a key that lives in the storage folder, so a
database dump alone does not reveal it. Losing the key file only means pasting the tokens again.

## 2026-10-31 — A video is never posted to Facebook twice

The reel's id and its MP4 are saved before the upload, and the moment Facebook is asked to
publish is saved before asking. A retry reads the reel's status first, because an attempt may
have reached Facebook whatever it reported. Scheduling uses Facebook's own scheduling; the app
has no posting timer.

## 2026-10-31 — Sessions are database tokens, not JWTs; users are disabled, never deleted

Sessions are opaque random tokens stored hashed in Postgres and last 30 days, sliding. Disabling
a user, forcing a password change and signing out every device then take effect immediately.
There is no self-signup and there are no roles: every member can manage users.

## 2026-10-31 — Prompt text is app data; the output format is code

Members edit the script and clone prompts and the banned words on `/knowledge`. The JSON output
format and its worked example stay in code (`claude.py`), so an edited prompt can never break
the parsing every job depends on.

## 2026-10-31 — Banned words warn, they never block the render

A banned word in the title scene, a scene, the caption or the pinned comment shows a yellow
warning only. Softer wording ("hỗ trợ", "tốt cho") is preferred over sensational claims, because
Meta flags or demonetizes medical wording even when the fact is true.

## 2026-10-31 — Affiliate products are approved by fixed rules

A product becomes approved only with a trusted shop type, at least 4.7 stars, at least 100 sales
and no banned word in its name. Editing an approved product sends it back to draft. The list is
entered by hand from the affiliate dashboard; there is no Shopee API call yet (see
[backlog.md](../backlog.md)).

## 2026-10-31 — Production: Coolify for api, worker and Postgres; Cloudflare Workers for web

The web app needs a server runtime for `proxy.ts` and the `/api/*` rewrite, which Cloudflare runs
through OpenNext on Workers (the Pages adapter is deprecated). Coolify auto-deploy stays off:
only CI deploys, after every test passes, api first (it runs the migrations), then the worker,
then the web.
