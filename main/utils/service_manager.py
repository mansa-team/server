import logging
import os
from config import Config, LOCALHOST_ADDRESSES
from main.utils.logging_config import limiter

import threading
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


class ServiceManager:
    _instances: dict[int, FastAPI] = {}
    _lock = threading.Lock()

    @classmethod
    def getApp(cls, port: int) -> FastAPI:
        if port in cls._instances:
            return cls._instances[port]

        with cls._lock:
            if port in cls._instances:
                return cls._instances[port]

            app = FastAPI(title=f"Mansa Service {port}")
            app.state.limiter = limiter

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

            cls._instances[port] = app
        return cls._instances[port]

    @classmethod
    def runAll(cls):
        logLevel = "error" if Config.DEBUG_MODE else "critical"

        def _runUvicorn(app: FastAPI, port: int, logLevel: str):
            uvicorn.run(app, host="0.0.0.0", port=port, log_level=logLevel)  # nosec: B104

        for port, app in cls._instances.items():
            thread = threading.Thread(target=_runUvicorn, args=(app, port, logLevel), daemon=True)
            thread.start()

            logger.info(f"Service running on port {port}")
