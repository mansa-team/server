# This file is kept for backward compatibility and to serve as a module entry point.
# The primary entry point for the FastAPI server is now main.py.

from config import Config, LOCALHOST_ADDRESSES
from main.utils.util import log
import time
import os

from main.utils.connectivity import checkMYSQLConnection, checkServiceConnection
from main.utils.service_manager import ServiceManager

from main.service.authentication_service import AuthenticationService
from main.service.user_service import UserService
from main.service.prometheus_service import PrometheusService
from main.service.scraper_service import ScraperService
from main.service.stocksapi_service import StocksAPIService

def orchestrator():
    log("system", "Warning: Running legacy orchestrator from __init__.py. Prefer main.py.")
    
    if not checkMYSQLConnection(): return

    if Config.USER['ENABLED'] and Config.USER['HOST'] in LOCALHOST_ADDRESSES:
        AuthenticationService.initialize(Config.USER['PORT'])
        UserService.initialize(Config.USER['PORT'])

    if Config.STOCKS_API['ENABLED'] and Config.STOCKS_API['HOST'] in LOCALHOST_ADDRESSES:
        StocksAPIService.initialize(Config.STOCKS_API['PORT'])

    if Config.PROMETHEUS['ENABLED'] and Config.PROMETHEUS['HOST'] in LOCALHOST_ADDRESSES:
        PrometheusService.initialize(Config.PROMETHEUS['PORT'])

    if Config.SCRAPER['ENABLED']:
        ScraperService.initialize()
        
    ServiceManager.runAll()

    if not checkServiceConnection("STOCKS_API") and Config.PROMETHEUS['ENABLED']:
        log("system", "Server initialization failed: Couldn't connect to the STOCKS_API in which Prometheus depends on.")
        return
    log("system", "Server initialized!")

    while True: time.sleep(1)

if __name__ == "__main__":
    orchestrator()
