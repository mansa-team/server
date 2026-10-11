from main.app.stocks_api.cache import stocksCache
from main.controller.stocksapi_controller import router as stocksRouter, stocksMcp
from main.utils.service_manager import getApp


class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(stocksRouter)

        mcpHttp = stocksMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        service.mount("/stocks/mcp", mcpHttp)
        service.router.lifespan_context = mcpHttp.lifespan

        stocksCache.cacheScheduler()
