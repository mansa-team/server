from config import Config

_issuerBase = f"http://{Config.USER.HOST}:{Config.USER.PORT}"
ISSUER_URL = _issuerBase
RESOURCE_URL = f"{_issuerBase}/wallet/mcp"
RESOURCE_METADATA_URL = f"{_issuerBase}/.well-known/oauth-protected-resource/wallet/mcp"
WALLET_SCOPE = "wallet"

revokedAccessJtis: set[str] = set()
