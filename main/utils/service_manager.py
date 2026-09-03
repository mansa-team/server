import logging
from config import Config
from main.utils.logging_config import limiter

import threading
import uvicorn
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from main.utils.request_id import RequestIDMiddleware

logger = logging.getLogger(__name__)

instances: dict[int, FastAPI] = {}


def getApp(port: int) -> FastAPI:
    if port in instances:
        return instances[port]

    app = FastAPI(title=f"Mansa Service {port}")
    app.state.limiter = limiter
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.add_middleware(RequestIDMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rateLimitExceededHandler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(status_code=429, content={"detail": "Too many requests", "error": str(exc.detail)})

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    instances[port] = app
    return app


def runAll():
    logLevel = "error" if Config.DEBUG_MODE else "critical"

    def runUvicorn(app: FastAPI, port: int, logLevel: str):
        uvicorn.run(app, host="0.0.0.0", port=port, log_level=logLevel)  # nosec: B104

    for port, app in instances.items():
        thread = threading.Thread(target=runUvicorn, args=(app, port, logLevel), daemon=True)
        thread.start()
        logger.info(f"Service running on port {port}")
