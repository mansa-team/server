"""Wallet service: HTTP routes plus the wallet MCP mount.

The MCP surface is an explicit operation-ID allowlist (WALLET_MCP_OPERATIONS):
seven read routes plus four LLM-shaped wrappers. Ledger writes stay off MCP
unless wrapped, and wallet creation/lookup is always server-side. The middleware
gates the compact convention on the X-MCP transport header only — plain HTTP
responses are untouched.
"""

import logging

from fastapi_mcp import FastApiMCP

from main.controller.wallet_controller import router as walletRouter
from main.utils.service_manager import getApp

logger = logging.getLogger(__name__)


class MCPDetectMiddleware:
    """Mark X-MCP requests (compact convention) without touching plain HTTP."""

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


# Explicit MCP tool allowlist (IDs come from each route's operation_id).
# Reads: positions/rebalance/summary/allocation/earnings/performance/progression.
# Wrappers: record_entry/set_rating/explain_twr/wallet_progression.
# Anything absent here cannot be called over MCP — entries PATCH/DELETE,
# wallets create/list and the raw ratings PUT stay HTTP-only.
WALLET_MCP_OPERATIONS = [
    "wallet_positions",
    "wallet_rebalance",
    "wallet_summary",
    "wallet_allocation",
    "wallet_earnings",
    "wallet_performance",
    "wallet_progression_series",
    "record_entry",
    "set_rating",
    "explain_twr",
    "wallet_progression",
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
