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
    return url


def allowed_origins() -> frozenset[str]:
    raw = read_env("ALLOWED_ORIGINS") or DEFAULT_ALLOWED_ORIGINS
    return frozenset(origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip())
