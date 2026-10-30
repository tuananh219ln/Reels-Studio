# Production image for the API, built by Coolify from the repo root (base directory /, Dockerfile
# /api/Dockerfile): the api uses reels_render for previews and text checks, so it installs ../worker too.
# Coolify sets DATABASE_URL, ALLOWED_ORIGINS, COOKIE_SECURE, PIXABAY_API_KEY and STORAGE_DIR.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# ffprobe checks uploaded scene clips and ffmpeg takes their preview frame; Debian's package, as in the worker.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY worker/pyproject.toml worker/
COPY worker/src worker/src
COPY api/pyproject.toml api/
COPY api/src api/src
# /data/storage is the shared volume; owned by the app user so a fresh volume is writable.
RUN pip install ./worker ./api && useradd --system --uid 10001 app && mkdir -p /data/storage && chown app /data/storage

COPY api/alembic.ini ./
COPY api/migrations ./migrations

USER app
EXPOSE 8000
# /api/me answers 401 without a session: any HTTP answer means the app is up.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 CMD python -c "import http.client as h; c = h.HTTPConnection('127.0.0.1', 8000, timeout=4); c.request('GET', '/api/me'); c.getresponse()"
# Migrations run on every start, before the app takes traffic; Alembic skips what is already applied.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn reels_api.main:create_app --factory --host 0.0.0.0 --port 8000"]
