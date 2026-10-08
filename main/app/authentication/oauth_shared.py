"""Shared wallet-OAuth identifiers + access-token revocation set (leaf).

Split out of mcp_oauth_provider/util so both sides import one direction
(util -> oauth_shared, provider -> oauth_shared, provider -> util) instead
of importing each other. Zero internal (main.*) imports: Config + stdlib only.

WalletOAuthProvider aliases its instance set to revokedAccessJtis, so the
module-level set here is the single source of truth in-process.
"""

from config import Config

_issuerBase = f"http://{Config.USER.HOST}:{Config.USER.PORT}"
ISSUER_URL = _issuerBase
RESOURCE_URL = f"{_issuerBase}/wallet/mcp"
RESOURCE_METADATA_URL = f"{_issuerBase}/.well-known/oauth-protected-resource/wallet/mcp"
WALLET_SCOPE = "wallet"

revokedAccessJtis: set[str] = set()
