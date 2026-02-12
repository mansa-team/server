from imports import *

from main.utils.connectivity import *
from main.service.stocksapi_service import *

from main.utils.connectivity import checkMYSQLConnection, checkServiceConnection
from main.utils.service_manager import ServiceManager
from main.service.stocksapi_service import StocksAPIService
from main.service.prometheus_service import PrometheusService

def orchestrator():
    # MYSQL Connection Test
    if not checkMYSQLConnection():
        return

    if Config.STOCKS_API['ENABLED'] == "TRUE" and Config.STOCKS_API['HOST'] in LOCALHOST_ADDRESSES:
        StocksAPIService.initialize(int(Config.STOCKS_API['PORT']))

    if Config.PROMETHEUS['ENABLED'] == "TRUE":
        PrometheusService.initialize(int(Config.PROMETHEUS['PORT']))

    ServiceManager.runAll()

    if not checkServiceConnection("STOCKS_API") and Config.PROMETHEUS['ENABLED'] == "TRUE":
        if Config.DEBUG_MODE == "TRUE":
            print("Server initialization failed: Couldn't connect to the STOCKS_API in which Prometheus depends on.")
        return
    
    while True: time.sleep(1)

if __name__ == "__main__":
    orchestrator()