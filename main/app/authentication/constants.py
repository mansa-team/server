from typing import Literal

ISSUER = "mansa-user"

CODE_TTL = 600
ACCESS_TTL = 3600
REFRESH_TTL = 2592000

TOKEN_EXPIRY_HOURS = 720
SESSION_EXPIRY_DAYS = 30
SESSION_IDLE_TIMEOUT_HOURS = 24

COOKIE_NAME = "mansa_token"
COOKIE_PATH = "/"
COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

WALLET_SCOPE = "wallet"
WALLET_RESOURCE_PATH = "/wallet/mcp"
