import logging
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
import uvicorn

from contextlib import asynccontextmanager

from tenacity import AsyncRetrying, RetryError, stop_after_attempt, wait_fixed

from config import Config, LOCALHOST_ADDRESSES
from main.utils.connectivity import checkDatabaseConnection, checkServiceConnection
from main.utils.service_manager import runAll
from main.utils.migrator import runMigrations
from main.utils.request_id import RequestIDMiddleware
from main.utils.errors import registerErrorHandlers

from main.service.authentication_service import AuthenticationService
from main.service.user_service import UserService
from main.service.prometheus_service import PrometheusService
from main.service.scraper_service import ScraperService, runScraper
from main.service.stocksapi_service import StocksAPIService

logger = logging.getLogger(__name__)
appStartTime = datetime.now()


@asynccontextmanager
async def lifespan(app: FastAPI):
    dbConnected = False
    try:
        async for attempt in AsyncRetrying(stop=stop_after_attempt(10), wait=wait_fixed(3)):
            with attempt:
                dbResults = checkDatabaseConnection()
                if all(r["status"] == "connected" for r in dbResults.values()):
                    dbConnected = True
                else:
                    logger.info(f"Retrying database connection ({attempt.retry_state.attempt_number}/10)")
                    raise ConnectionError("database not ready")
            if dbConnected:
                break
    except RetryError:
        logger.error("Database connection failed after retries.")
    else:
        runMigrations()

    services = [
        ("USER", Config.USER, lambda port: (AuthenticationService.initialize(port), UserService.initialize(port))),
        ("STOCKS_API", Config.STOCKS_API, StocksAPIService.initialize),
        ("PROMETHEUS", Config.PROMETHEUS, PrometheusService.initialize),
    ]
    for name, config, init in services:
        if config.ENABLED:
            if config.HOST in LOCALHOST_ADDRESSES:
                init(config.PORT)
            elif not checkServiceConnection(name):
                logger.error(f"Remote connection to the {name} Service failed")

    if Config.SCRAPER.ENABLED:
        ScraperService.initialize()

    runAll()
    logger.info("All services initialized!")

    yield


app = FastAPI(title="Mansa Server", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
registerErrorHandlers(app)


@app.get("/health")
async def health():
    return {"status": "ok", "message": "Mansa Server is running"}


@app.get("/status")
async def status():
    uptime = datetime.now() - appStartTime
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    databases = checkDatabaseConnection()

    services = {}
    for name, config in [
        ("user", Config.USER),
        ("stocks_api", Config.STOCKS_API),
        ("prometheus", Config.PROMETHEUS),
    ]:
        if not config.ENABLED:
            services[name] = {"status": "disabled"}
            continue
        isLocal = config.HOST in LOCALHOST_ADDRESSES
        services[name] = {"status": "running", "port": config.PORT, "type": "local" if isLocal else "remote"}
        if not isLocal:
            services[name]["host"] = config.HOST

    if Config.SCRAPER.ENABLED:
        services["scraper"] = {"status": "running", "type": "local"}

    return {
        "status": "healthy" if all(r["status"] == "connected" for r in databases.values()) else "degraded",
        "uptime": f"{days}d {hours}h {minutes}m {seconds}s",
        "databases": databases,
        "services": services,
    }


@app.post("/scraper/run")
async def triggerScraper(background_tasks: BackgroundTasks):
    if not Config.DEBUG_MODE:
        return {"status": "error", "message": "Scraper trigger is only available in debug mode"}
    background_tasks.add_task(runScraper)
    return {"status": "ok", "message": "Scraper triggered in background (debug mode only)"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
