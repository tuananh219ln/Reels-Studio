# Production image for the API, built by Coolify from docker-compose.coolify.yml.
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
# Migrations run on every start, before the app takes traffic; Alembic skips what is already applied.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn reels_api.main:create_app --factory --host 0.0.0.0 --port 8000"]
