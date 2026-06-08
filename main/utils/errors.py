import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from main.utils.request_id import request_id_var


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
    request_id: str | None = None
    timestamp: str
    status_code: int


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        return True


def _build_error_response(status_code: int, error: str, detail: str | None = None) -> dict:
    return ErrorResponse(
        error=error,
        detail=detail,
        request_id=request_id_var.get(""),
        timestamp=datetime.now(timezone.utc).isoformat(),
        status_code=status_code,
    ).model_dump()


async def http_exception_handler(request: Request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_response(exc.status_code, str(exc.detail)),
    )


async def validation_exception_handler(request: Request, exc):
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(part) for part in error.get("loc", []))
        errors.append({"field": loc, "message": error.get("msg", "")})

    return JSONResponse(
        status_code=422,
        content=_build_error_response(422, "Validation error", detail=str(errors)),
    )


async def generic_exception_handler(request: Request, exc):
    logger = logging.getLogger("main.errors")
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=_build_error_response(500, "Internal server error"),
    )


def register_error_handlers(app: FastAPI):
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
