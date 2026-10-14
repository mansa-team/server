from main.app.stocks_api.cache import stocksCache
from main.controller.stocksapi_controller import router as stocksRouter
from main.controller.stocksapi_controller import mcp as stocksMcp
from main.utils.service_manager import adoptMcpLifespan, getApp


class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(stocksRouter)

        mcpHttp = stocksMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        service.mount("/stocks/mcp", mcpHttp)
        adoptMcpLifespan(service, mcpHttp)

        stocksCache.cacheScheduler()
