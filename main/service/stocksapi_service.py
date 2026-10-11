"""Stocks service: HTTP routes plus the stocks MCP server mount.

The MCP surface (five hand-written tools) lives in
main.controller.stocksapi_controller.buildStocksMCP next to the route functions
it delegates to; this service only mounts it at /stocks/mcp and adopts its
lifespan.
"""

from main.app.stocks_api.cache import stocksCache
from main.controller.stocksapi_controller import buildStocksMCP
from main.controller.stocksapi_controller import router as stocksRouter
from main.utils.service_manager import getApp


class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(stocksRouter)

        stocksMcp = buildStocksMCP()
        mcpApp = stocksMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        service.mount("/stocks/mcp", mcpApp)
        # Mounted sub-app lifespans never run under uvicorn: adopt it so the
        # streamable session manager is initialized for POST traffic.
        service.router.lifespan_context = mcpApp.lifespan

        stocksCache.cacheScheduler()
