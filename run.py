import logging
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks

from contextlib import asynccontextmanager
import asyncio

from config import Config, LOCALHOST_ADDRESSES
from main.utils.connectivity import checkDatabaseConnection, checkServiceConnection
from main.utils.service_manager import ServiceManager
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
    for i in range(10):
        if checkDatabaseConnection():
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

    dbOk = checkDatabaseConnection()

    services = {}
    for name, config in [
        ("user", Config.USER),
        ("stocks_api", Config.STOCKS_API),
        ("prometheus", Config.PROMETHEUS),
    ]:
        if not config["ENABLED"]:
            services[name] = {"status": "disabled"}
            continue
        isLocal = config["HOST"] in LOCALHOST_ADDRESSES
        services[name] = {"status": "running", "port": config["PORT"], "type": "local" if isLocal else "remote"}
        if not isLocal:
            services[name]["host"] = config["HOST"]

    if Config.SCRAPER["ENABLED"]:
        services["scraper"] = {"status": "running", "type": "local"}

    return {
        "status": "healthy" if dbOk else "degraded",
        "uptime": f"{days}d {hours}h {minutes}m {seconds}s",
        "services": services,
    }


@app.post("/scraper/run")
async def triggerScraper(background_tasks: BackgroundTasks):
    if not Config.DEBUG_MODE:
        return {"status": "error", "message": "Scraper trigger is only available in debug mode"}
    background_tasks.add_task(runScraper)
    return {"status": "ok", "message": "Scraper triggered in background (debug mode only)"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
