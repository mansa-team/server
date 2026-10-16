from main.app.authentication.csrf import CsrfProtectMiddleware
from main.controller.wallet_controller import router as walletRouter
from main.controller.wallet_controller import mcp as walletMcp
from main.utils.service_manager import adoptMcpLifespan, getApp


class WalletService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port, middleware=[CsrfProtectMiddleware])
        service.include_router(walletRouter)

        mcpHttp = walletMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        service.mount("/wallet/mcp", mcpHttp)
        adoptMcpLifespan(service, mcpHttp)
