import importlib
import pkgutil

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from . import config
from .errors import ApiError, api_error_handler, database_error_handler, error_body, validation_error_handler

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def routers() -> list[APIRouter]:
    """Every `routes_*.py` module's `router`, by file name: a new module is served without editing this file."""
    package = importlib.import_module(__package__)
    names = sorted(m.name for m in pkgutil.iter_modules(package.__path__) if m.name.startswith("routes_"))
    return [importlib.import_module(f"{__package__}.{name}").router for name in names]


def create_app() -> FastAPI:
    app = FastAPI(title="Reels Studio API", docs_url=None, redoc_url=None, openapi_url=None)
    allowed_origins = config.allowed_origins()

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        # CSRF guard: the web app proxies /api through Next.js, so browsers always send its Origin.
        if request.method in UNSAFE_METHODS:
            origin = (request.headers.get("origin") or "").rstrip("/")
            if origin not in allowed_origins:
                return JSONResponse(
                    error_body("origin_not_allowed", "Yêu cầu không đến từ Reels Studio"), status_code=403
                )
        return await call_next(request)

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(OperationalError, database_error_handler)
    for router in routers():
        app.include_router(router)
    return app
