from main.utils.service_manager import getApp
from main.controller.authentication_controller import router as authenticationRouter


class AuthenticationService:
    @staticmethod
    def oauthRoutes():
        """SDK-native AS routes (DCR + metadata + token/refresh/revoke, Starlette)."""
        from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
        from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
        from pydantic import AnyHttpUrl

        from main.app.authentication.mcp_oauth_provider import (
            ISSUER_URL,
            RESOURCE_URL,
            WALLET_SCOPE,
            walletOAuthProvider,
        )

        return create_auth_routes(
            walletOAuthProvider,
            issuer_url=AnyHttpUrl(ISSUER_URL),
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=[WALLET_SCOPE],
                default_scopes=[WALLET_SCOPE],
            ),
            revocation_options=RevocationOptions(enabled=True),
        ) + create_protected_resource_routes(
            resource_url=AnyHttpUrl(RESOURCE_URL),
            authorization_servers=[AnyHttpUrl(ISSUER_URL)],
            scopes_supported=[WALLET_SCOPE],
        )

    @staticmethod
    def initialize(port: int):
        service = getApp(port)

        service.include_router(authenticationRouter)
        # Added after the MCP construction in WalletService so the operation
        # scan only sees the 11 allowlisted wallet operations (tool count unchanged).
        service.routes.extend(AuthenticationService.oauthRoutes())
