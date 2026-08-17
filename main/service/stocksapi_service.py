from fastapi_mcp import FastApiMCP
from fastapi.middleware.gzip import GZipMiddleware

from main.utils.service_manager import getApp
from main.controller.stocksapi_controller import router as stocksRouter

from main.app.stocks_api.cache import stocksCache


class MCPDetectMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"x-mcp") == b"true":
                scope.setdefault("state", {})["compressed"] = True
                # X-MCP requests are always compact — force the flag so cache keys and handlers agree
                qs = scope.get("query_string", b"").decode("latin-1")
                if "compact=" not in qs:
                    scope["query_string"] = (qs + ("&" if qs else "") + "compact=true").encode("latin-1")
        await self.app(scope, receive, send)


class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.add_middleware(MCPDetectMiddleware)
        service.include_router(stocksRouter)
        service.add_middleware(GZipMiddleware, minimum_size=4096, compresslevel=3)

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
