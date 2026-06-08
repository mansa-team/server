import logging
from fastapi import FastAPI, BackgroundTasks
from contextlib import asynccontextmanager
import asyncio
import os
from config import Config, LOCALHOST_ADDRESSES
from main.utils.logging_config import limiter
from main.utils.connectivity import checkMySqlConnection, checkServiceConnection
from main.utils.service_manager import ServiceManager
from main.utils.migrator import runMigrations
from main.utils.request_id import RequestIDMiddleware
from main.utils.errors import register_error_handlers

from main.service.authentication_service import AuthenticationService
from main.service.user_service import UserService
from main.service.prometheus_service import PrometheusService
from main.service.scraper_service import ScraperService, runScraper
from main.service.stocksapi_service import StocksAPIService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    dbConnected = False
    for i in range(10):
        if checkMySqlConnection():
            dbConnected = True
            break
        logger.info(f"Retrying database connection ({i + 1}/10)")
        await asyncio.sleep(3)

    if not dbConnected:
        logger.error("Database connection failed after retries.")
    else:
        runMigrations()

    if Config.USER["ENABLED"]:
        if Config.USER["HOST"] in LOCALHOST_ADDRESSES:
            AuthenticationService.initialize(Config.USER["PORT"])
            UserService.initialize(Config.USER["PORT"])
        else:
            if not checkServiceConnection("USER"):
                logger.error("Remote connection to the USER Service failed")

    if Config.STOCKS_API["ENABLED"]:
        if Config.STOCKS_API["HOST"] in LOCALHOST_ADDRESSES:
            StocksAPIService.initialize(Config.STOCKS_API["PORT"])
        else:
            if not checkServiceConnection("STOCKS_API"):
                logger.error("Remote connection to the STOCKS_API Service failed")

    if Config.PROMETHEUS["ENABLED"]:
        if Config.PROMETHEUS["HOST"] in LOCALHOST_ADDRESSES:
            PrometheusService.initialize(Config.PROMETHEUS["PORT"])
        else:
            if not checkServiceConnection("PROMETHEUS"):
                logger.error("Remote connection to the PROMETHEUS Service failed")

    if Config.SCRAPER["ENABLED"]:
        ScraperService.initialize()

    ServiceManager.runAll()
    logger.info("All services initialized!")

    yield


app = FastAPI(title="Mansa Server", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
register_error_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok", "message": "Mansa Server is running"}


@app.post("/scraper/run")
async def triggerScraper(background_tasks: BackgroundTasks):
    if not Config.DEBUG_MODE:
        return {"status": "error", "message": "Scraper trigger is only available in debug mode"}
    background_tasks.add_task(runScraper)
    return {"status": "ok", "message": "Scraper triggered in background (debug mode only)"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
