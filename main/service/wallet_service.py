"""Wallet service: HTTP routes plus the wallet MCP server mount.

The MCP surface (eleven hand-written tools) lives in
main.controller.wallet_controller.walletMcp next to the route functions
it delegates to; this service only mounts it at /wallet/mcp and adopts its
lifespan. Wallet responses have no compact form: plain HTTP and MCP serve
the same JSON.
"""

from main.controller.wallet_controller import router as walletRouter, walletMcp
from main.utils.service_manager import getApp


class WalletService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(walletRouter)

        mcpHttp = walletMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        service.mount("/wallet/mcp", mcpHttp)
        # Mounted sub-app lifespans never run under uvicorn: adopt it so the
        # streamable session manager is initialized for POST traffic.
        service.router.lifespan_context = mcpHttp.lifespan
