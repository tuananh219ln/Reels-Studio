import os
from pathlib import Path

# api/src/reels_api/config.py -> the repo root holds .env (same file the worker reads)
DOTENV_PATH = Path(__file__).resolve().parents[3] / ".env"

DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000"


class ConfigError(Exception):
    pass


def read_env(name: str) -> str:
    """A real environment variable wins over .env, even when it is set to an empty string
    (same rule as worker/src/reels_render/env.py)."""
    if name in os.environ:
        return os.environ[name].strip()
    return _read_dotenv(DOTENV_PATH).get(name, "")


def _read_dotenv(path: Path) -> dict[str, str]:
    try:
        # utf-8-sig drops the BOM that PowerShell's Out-File writes.
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        name, separator, value = line.partition("=")
        if not separator or line.startswith("#"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name.strip()] = value
    return values


def database_url() -> str:
    url = read_env("DATABASE_URL")
    if not url:
        raise ConfigError("Chưa cấu hình DATABASE_URL: chép .env.example thành .env ở thư mục gốc repo")
    # Coolify shows Postgres URLs without a driver; the app always talks to Postgres through psycopg 3.
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url.removeprefix(scheme)
    return url


def allowed_origins() -> frozenset[str]:
    raw = read_env("ALLOWED_ORIGINS") or DEFAULT_ALLOWED_ORIGINS
    return frozenset(origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip())


def cookie_secure() -> bool:
    """Production serves the app over HTTPS only, so the session cookie gets the Secure flag there."""
    return read_env("COOKIE_SECURE").lower() in {"1", "true", "yes"}


def storage_dir() -> Path:
    """Root of uploaded and generated files; shared by the api and the worker (one volume in production)."""
    raw = read_env("STORAGE_DIR")
    return Path(raw) if raw else DOTENV_PATH.parent / "data" / "storage"


def pixabay_key() -> str:
    return read_env("PIXABAY_API_KEY")


def pixabay_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return read_env("PIXABAY_API_URL") or "https://pixabay.com/api/"


def claude_model() -> str:
    return read_env("CLAUDE_MODEL") or "claude-sonnet-5-5"
