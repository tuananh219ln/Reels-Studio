# Production image for the API, built by Coolify (Dockerfile build pack, base directory /api).
# Coolify sets DATABASE_URL, ALLOWED_ORIGINS and COOKIE_SECURE.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install . && useradd --system --uid 10001 app

COPY alembic.ini ./
COPY migrations ./migrations

USER app
EXPOSE 8000
# /api/me answers 401 without a session: any HTTP answer means the app is up.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 CMD python -c "import http.client as h; c = h.HTTPConnection('127.0.0.1', 8000, timeout=4); c.request('GET', '/api/me'); c.getresponse()"
# Migrations run on every start, before the app takes traffic; Alembic skips what is already applied.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn reels_api.main:create_app --factory --host 0.0.0.0 --port 8000"]
