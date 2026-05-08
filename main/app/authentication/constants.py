from typing import Literal
from config import Config

SECRET_KEY = Config.USER["JWT_SECRET_KEY"]
ALGORITHM = "HS256"

SESSION_EXPIRY_DAYS = 30
TOKEN_EXPIRY_HOURS = SESSION_EXPIRY_DAYS * 24

COOKIE_NAME = "mansa_token"
COOKIE_PATH = "/"
COOKIE_SAMESITE: Literal["lax", "strict", "none"] | None = "lax"
