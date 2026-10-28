from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from . import config
from .errors import ApiError, api_error_handler, database_error_handler, error_body, validation_error_handler
from .routes_auth import router as auth_router
from .routes_users import router as users_router

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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
    app.include_router(auth_router)
    app.include_router(users_router)
    return app
