from imports import *
from main.utils.util import log
from main.utils.connectivity import checkMYSQLConnection, checkServiceConnection
from main.utils.service_manager import ServiceManager

from main.service.authentication_service import AuthenticationService
from main.service.stocksapi_service import StocksAPIService
from main.service.prometheus_service import PrometheusService
from main.service.scraper_service import ScraperService

def orchestrator():
    if not checkMYSQLConnection(): return

    if Config.AUTH['ENABLED'] == "TRUE" and Config.AUTH['HOST'] in LOCALHOST_ADDRESSES:
        AuthenticationService.initialize(int(Config.AUTH['PORT']))

    if Config.STOCKS_API['ENABLED'] == "TRUE" and Config.STOCKS_API['HOST'] in LOCALHOST_ADDRESSES:
        StocksAPIService.initialize(int(Config.STOCKS_API['PORT']))

    if Config.PROMETHEUS['ENABLED'] == "TRUE" and Config.PROMETHEUS['HOST'] in LOCALHOST_ADDRESSES:
        PrometheusService.initialize(int(Config.PROMETHEUS['PORT']))

    if Config.SCRAPER['ENABLED'] == "TRUE":
        ScraperService.initialize()
        
    ServiceManager.runAll()

    if not checkServiceConnection("STOCKS_API") and Config.PROMETHEUS['ENABLED'] == "TRUE":
        log("system", "Server initialization failed: Couldn't connect to the STOCKS_API in which Prometheus depends on.")
        return
    
    log("system", "Server initialized!")

    while True: time.sleep(1)

if __name__ == "__main__":
    orchestrator()