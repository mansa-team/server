import logging

from fastapi_mcp import FastApiMCP

from main.controller.wallet_controller import router as walletRouter
from main.utils.service_manager import getApp

logger = logging.getLogger(__name__)


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

WALLET_MCP_OPERATIONS = [
    "wallet_positions",
    "wallet_rebalance",
    "wallet_summary",
    "wallet_allocation",
    "wallet_earnings",
    "wallet_performance",
    "wallet_progression_series",
]


class WalletService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.add_middleware(MCPDetectMiddleware)
        service.include_router(walletRouter)

        mcp = FastApiMCP(
            service,
            name="Mansa Wallet MCP",
            include_operations=WALLET_MCP_OPERATIONS,
            headers=["authorization", "x-mcp"],
        )
        mcp.mount_http(service, mount_path="/wallet/mcp")
