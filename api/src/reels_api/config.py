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


def pexels_key() -> str:
    return read_env("PEXELS_API_KEY")


def pexels_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return (read_env("PEXELS_API_URL") or "https://api.pexels.com").rstrip("/")


def openverse_api_url() -> str:
    # No key needed: Openverse answers anonymous calls. Overridable only so tests and E2E can point
    # at a local fake; production uses the default.
    return (read_env("OPENVERSE_API_URL") or "https://api.openverse.org").rstrip("/")


def openverse_client_id() -> str:
    return read_env("OPENVERSE_CLIENT_ID")


def openverse_client_secret() -> str:
    return read_env("OPENVERSE_CLIENT_SECRET")


def image_gen_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return (read_env("IMAGE_GEN_API_URL") or "https://generativelanguage.googleapis.com").rstrip("/")


def image_gen_model() -> str:
    # Gemini image generation via Google AI Studio (owner's choice, 2026-10-31).
    return read_env("IMAGE_GEN_MODEL") or "gemini-2.5-flash-image"


def image_gen_cf_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return (read_env("IMAGE_GEN_CF_API_URL") or "https://api.cloudflare.com/client/v4").rstrip("/")


def image_gen_cf_account_id() -> str:
    # The Cloudflare account's ID (not a secret), shown on the dashboard.
    return read_env("IMAGE_GEN_CF_ACCOUNT_ID")


def image_gen_cf_model() -> str:
    return read_env("IMAGE_GEN_CF_MODEL") or "@cf/black-forest-labs/flux-1-schnell"


def image_inpaint_cf_model() -> str:
    # "Sửa ảnh" › "Xóa vùng" with Cloudflare (image_edit.py): an inpainting model, on the same account and token.
    return read_env("IMAGE_INPAINT_CF_MODEL") or "@cf/runwayml/stable-diffusion-v1-5-inpainting"


def lama_model_path() -> str:
    # "Sửa ảnh" › "Xóa vùng" on the worker itself (image_edit.py): LaMa as ONNX, baked into the worker image.
    return read_env("LAMA_MODEL_PATH")


def claude_model() -> str:
    return read_env("CLAUDE_MODEL") or "claude-sonnet-5-5"


# ElevenLabs "Adam", a premade voice every account has.
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"


def facebook_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return (read_env("FACEBOOK_API_URL") or "https://graph.facebook.com/v26.0").rstrip("/")


def shopee_affiliate_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return (read_env("SHOPEE_AFFILIATE_API_URL") or "https://open-api.affiliate.shopee.vn/graphql").rstrip("/")


def shopee_short_link_url() -> str:
    # Where a pasted short link (s.shopee.vn/<code>) is asked for its redirect. Overridable only so tests and E2E can
    # point at a local fake; production uses the default.
    return (read_env("SHOPEE_SHORT_LINK_URL") or "https://s.shopee.vn").rstrip("/")


def tiktok_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return (read_env("TIKTOK_API_URL") or "https://open.tiktokapis.com").rstrip("/")


def tiktok_client_key() -> str:
    # The TikTok developer app's own identity (Login Kit + Content Posting API), not a member's: one for the team.
    # The Sandbox has a key and secret of its own, set in these same two variables while recording the demo.
    return read_env("TIKTOK_CLIENT_KEY")


def tiktok_client_secret() -> str:
    return read_env("TIKTOK_CLIENT_SECRET")


def elevenlabs_api_url() -> str:
    # Overridable only so tests and E2E can point at a local fake; production uses the default.
    return (read_env("ELEVENLABS_API_URL") or "https://api.elevenlabs.io").rstrip("/")


def vieneu_api_url() -> str:
    # VieNeu's cloud API, the voices whose id starts with "vieneu:" (tts.py). Overridable only so tests and E2E can
    # point at a local fake; production uses the default.
    return (read_env("VIENEU_API_URL") or "https://api.vieneu.io/api").rstrip("/")


def voice_id() -> str:
    return read_env("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID


def voice_model() -> str:
    # eleven_multilingual_v2 does not speak Vietnamese; v3 and the v2.5 models do.
    return read_env("ELEVENLABS_MODEL") or "eleven_v3"
