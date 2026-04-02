from fastapi import FastAPI
from contextlib import asynccontextmanager
from config import Config, LOCALHOST_ADDRESSES
from main.utils.util import log
from main.utils.connectivity import checkMYSQLConnection, checkServiceConnection
from main.utils.service_manager import ServiceManager
import asyncio
import os

from main.service.authentication_service import AuthenticationService
from main.service.user_service import UserService
from main.service.prometheus_service import PrometheusService
from main.service.scraper_service import ScraperService
from main.service.stocksapi_service import StocksAPIService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    log("system", "Starting services...")
    
    if not checkMYSQLConnection():
        log("system", "Critical: Database connection failed. Some services might not work correctly.")

    # Selectively start services based on environment and config
    # This allows decoupling the API from the Scraper in Docker
    
    if Config.USER['ENABLED'] and Config.USER['HOST'] in LOCALHOST_ADDRESSES:
        log("system", "Initializing User Services...")
        AuthenticationService.initialize(Config.USER['PORT'])
        UserService.initialize(Config.USER['PORT'])

    if Config.STOCKS_API['ENABLED'] and Config.STOCKS_API['HOST'] in LOCALHOST_ADDRESSES:
        log("system", "Initializing Stocks API Service...")
        StocksAPIService.initialize(Config.STOCKS_API['PORT'])

    if Config.PROMETHEUS['ENABLED'] and Config.PROMETHEUS['HOST'] in LOCALHOST_ADDRESSES:
        log("system", "Initializing Prometheus Service...")
        PrometheusService.initialize(Config.PROMETHEUS['PORT'])

    # The Scraper can be toggled via environment variable for Docker decoupling
    run_scraper = os.getenv("RUN_SCRAPER", "true").lower() == "true"
    if Config.SCRAPER['ENABLED'] and run_scraper:
        log("system", "Initializing Scraper Service...")
        ScraperService.initialize()
        
    ServiceManager.runAll()

    if not checkServiceConnection("STOCKS_API") and Config.PROMETHEUS['ENABLED']:
        log("system", "Warning: Couldn't connect to STOCKS_API which Prometheus depends on.")
    
    log("system", "All services initialized!")
    
    yield
    
    # SHUTDOWN
    log("system", "Shutting down services...")
    # Add any explicit shutdown logic here if needed

app = FastAPI(title="Mansa Server", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Mansa Server is running"}

if __name__ == "__main__":
    import uvicorn
    # Use environment variables for host and port if available
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host=host, port=port)
