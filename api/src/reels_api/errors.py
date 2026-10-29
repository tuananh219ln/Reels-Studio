import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

log = logging.getLogger(__name__)


class ApiError(Exception):
    """An expected refusal: a fixed HTTP status, a stable code for the web app and a Vietnamese message."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default 422 echoes the submitted values back, which would include passwords.
    return JSONResponse(error_body("invalid_request", "Dữ liệu gửi lên không hợp lệ"), status_code=422)


async def database_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
    log.warning("Database unavailable: %s", type(exc.orig).__name__ if exc.orig else type(exc).__name__)
    return JSONResponse(
        error_body("database_unavailable", "Không kết nối được cơ sở dữ liệu, thử lại sau"), status_code=503
    )
