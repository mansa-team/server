from typing import Literal

SESSION_EXPIRY_DAYS = 30
TOKEN_EXPIRY_HOURS = SESSION_EXPIRY_DAYS * 24

COOKIE_NAME = "mansa_token"
COOKIE_PATH = "/"
COOKIE_SAMESITE: Literal["lax", "strict", "none"] | None = "lax"
