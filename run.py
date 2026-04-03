from fastapi import FastAPI
from contextlib import asynccontextmanager
from config import Config, LOCALHOST_ADDRESSES
from main.utils.util import log
from main.utils.connectivity import checkMYSQLConnection, checkServiceConnection
from main.utils.service_manager import ServiceManager
from main.utils.migrator import runMigrations
import asyncio
import os

from main.service.authentication_service import AuthenticationService
from main.service.user_service import UserService
from main.service.prometheus_service import PrometheusService
from main.service.scraper_service import ScraperService
from main.service.stocksapi_service import StocksAPIService

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_connected = False
    for i in range(10):
        if checkMYSQLConnection():
            db_connected = True
            break
        log("system", f"Retrying database connection ({i+1}/10)")
        await asyncio.sleep(3)

    if not db_connected:
        log("system", "Database connection failed after retries.")
    else: runMigrations()
    
    if Config.USER['ENABLED']:
        if Config.USER['HOST'] in LOCALHOST_ADDRESSES:
            AuthenticationService.initialize(Config.USER['PORT'])
            UserService.initialize(Config.USER['PORT'])
        else:
            if not checkServiceConnection("USER"): log("system", "Remote connection to the USER Service failed")

    if Config.STOCKS_API['ENABLED']:
        if Config.STOCKS_API['HOST'] in LOCALHOST_ADDRESSES:
            StocksAPIService.initialize(Config.STOCKS_API['PORT'])
        else:
            if not checkServiceConnection("STOCKS_API"): log("system", "Remote connection to the STOCKS_API Service failed")

    if Config.PROMETHEUS['ENABLED']: 
        if Config.PROMETHEUS['HOST'] in LOCALHOST_ADDRESSES:
            PrometheusService.initialize(Config.PROMETHEUS['PORT'])
        else:
            if not checkServiceConnection("PROMETHEUS"): log("system", "Remote connection to the PRONETHEUS Service failed")

    if Config.SCRAPER['ENABLED']:
        ScraperService.initialize()
        
    ServiceManager.runAll()
    log("system", "All services initialized!")
    
    yield
app = FastAPI(title="Mansa Server", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Mansa Server is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)