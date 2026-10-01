import logging

import fastapi_mcp.server as fastapiMcpServer
from fastapi_mcp import FastApiMCP
from fastapi.middleware.gzip import GZipMiddleware
import mcp.types as mcpTypes
from mcp.server.lowlevel.server import Server as McpServer

from main.utils.service_manager import getApp
from main.controller.stocksapi_controller import router as stocksRouter

from main.app.stocks_api.cache import stocksCache

logger = logging.getLogger(__name__)


needsBridge = not hasattr(McpServer, "list_tools")


class CompatServer(McpServer):
    """Accept fastapi-mcp 0.4.0's positional (name, description) + decorator API on mcp>=2 (keyword-only, callbacks)."""

    def __init__(self, name: str, description: str | None = None, **kwargs):
        if needsBridge:
            self.listToolsHandler = None
            self.callToolHandler = None

            async def onListTools(requestContext, params):
                return mcpTypes.ListToolsResult(tools=await self.listToolsHandler())

            async def onCallTool(requestContext, params):
                content = await self.callToolHandler(params.name, params.arguments or {})
                return mcpTypes.CallToolResult(content=list(content))

            super().__init__(
                name,
                description=description,
                on_list_tools=onListTools,
                on_call_tool=onCallTool,
                **kwargs,
            )
        else:
            try:
                super().__init__(name, description=description, **kwargs)
            except TypeError:
                super().__init__(name, description or "", **kwargs)

    if needsBridge:

        def list_tools(self):
            def decorator(handler):
                self.listToolsHandler = handler
                return handler

            return decorator

        def call_tool(self):
            def decorator(handler):
                self.callToolHandler = handler
                return handler

            return decorator


fastapiMcpServer.Server = CompatServer


class MCPDetectMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"x-mcp") == b"true":
                scope.setdefault("state", {})["compressed"] = True
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
