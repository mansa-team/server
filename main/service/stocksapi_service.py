from main.utils.service_manager import ServiceManager
from main.controller.stocksapi_controller import router as stocks_router
from main.app.stocks_api.cache import cacheScheduler

from imports import dbEngine

class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(stocks_router)

        cacheScheduler(dbEngine)