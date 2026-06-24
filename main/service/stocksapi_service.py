from fastapi_mcp import FastApiMCP

from main.utils.service_manager import ServiceManager
from main.controller.stocksapi_controller import router as stocksRouter

from main.app.stocks_api.cache import stocksCache


class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(stocksRouter)

        mcp = FastApiMCP(
            service,
            name="Mansa's Stocks API MCP",
            include_operations=[
                "listFields_stocks_fields_get",
                "getHistorical_stocks_historical_get",
                "getFundamental_stocks_fundamental_get",
                "getCotations_stocks_cotations_get",
                "getLiveCotation_stocks_cotations_live_get",
            ],
        )
        mcp.mount_http(service, mount_path="/stocks/mcp")

        stocksCache.cacheScheduler()
