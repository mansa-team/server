import logging
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from main.utils.request_id import requestIdVar


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = requestIdVar.get("")
        return True


def buildErrorResponse(statusCode: int, error: str, detail: str | None = None) -> dict:
    return {
        "success": False,
        "error": error,
        "detail": detail,
        "request_id": requestIdVar.get(""),
        "timestamp": datetime.now().isoformat(),
        "status_code": statusCode,
    }


async def httpExceptionHandler(request: Request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=buildErrorResponse(exc.status_code, str(exc.detail)),
    )


async def validationExceptionHandler(request: Request, exc):
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(part) for part in error.get("loc", []))
        errors.append({"field": loc, "message": error.get("msg", "")})

    return JSONResponse(
        status_code=422,
        content=buildErrorResponse(422, "Validation error", detail=str(errors)),
    )


async def genericExceptionHandler(request: Request, exc):
    logger = logging.getLogger("main.errors")
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=buildErrorResponse(500, "Internal server error"),
    )


def registerErrorHandlers(app: FastAPI):
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_exception_handler(StarletteHTTPException, httpExceptionHandler)
    app.add_exception_handler(RequestValidationError, validationExceptionHandler)
    app.add_exception_handler(Exception, genericExceptionHandler)
