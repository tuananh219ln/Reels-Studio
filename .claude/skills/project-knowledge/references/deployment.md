# Deployment & Operations

## Current State

The project runs locally only. There is no production server, domain, or CI/CD deployment yet.
The owner will deploy later.

**Development host:** the owner's Linux machine (Intel i5-10400F, 6 cores / 12 threads, 15 GiB
RAM). Docker Engine + Compose must be installed first; as of 2026-10-28 neither Docker nor FFmpeg
was present on the host (FFmpeg is not needed there, see
[architecture.md](architecture.md#external-integrations)).

**Runtime:** Docker Compose runs `web`, `api`, `worker`, `postgres`, and `redis`, plus the storage
volume (see [architecture.md](architecture.md#components)). The same compose setup is the planned
production setup on a single VPS.

## Environment Variables

**See:** [.env.example](../../../../.env.example). It is still empty and must be filled in by the
scaffold.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API |
| `CLAUDE_MODEL` | Model override; the default is `claude-sonnet-5-5` |
| `PEXELS_API_KEY`, `PIXABAY_API_KEY` | Stock image search |
| `TTS_PROVIDER` | `edge` or `azure` |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | Needed only when `TTS_PROVIDER=azure` |
| `DATABASE_URL`, `REDIS_URL` | Service connections |
| `STORAGE_DIR` | Root of the media storage volume |
| `RENDER_CONCURRENCY` | Maximum parallel render jobs; the default is 1 |
| `SESSION_SECRET` | Auth session signing |

These names are planned and will be finalized at scaffold time. After that, keep this table in
sync with `.env.example`.

## Operations

- **First account:** created by a CLI command. After that, members create accounts in the app.
- **Storage growth:** each video is about 10–30 MB, which is about 1–3 GB/month at 3 videos/day.
  There is no cleanup in the MVP.

Not yet defined: production host, delivery path, rollback, monitoring, and backups. Fill these in
when the VPS deployment is specified.
