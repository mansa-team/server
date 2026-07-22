from fastapi_mcp import FastApiMCP
from starlette.requests import Request

from main.utils.service_manager import ServiceManager
from main.controller.stocksapi_controller import router as stocksRouter

from main.app.stocks_api.cache import stocksCache


class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)

        @service.middleware("http")
        async def mcpDetect(request: Request, call_next):
            request.state.compressed = request.headers.get("x-mcp") == "true"
            return await call_next(request)

        service.include_router(stocksRouter)

        mcp = FastApiMCP(
            service,
            name="Mansa's Stocks API MCP",
            include_operations=[
                "list_fields",
                "get_historical",
                "get_fundamental",
                "get_cotations",
                "get_live_price",
            ],
            headers=["authorization", "x-mcp"],
        )
        mcp.mount_http(service, mount_path="/stocks/mcp")

        stocksCache.cacheScheduler()
