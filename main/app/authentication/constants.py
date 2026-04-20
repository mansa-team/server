from typing import Literal
from config import Config

SECRET_KEY = Config.USER["JWT_SECRET_KEY"]
ALGORITHM = "HS256"

TOKEN_EXPIRY_HOURS = 24

COOKIE_NAME = "mansa_token"
COOKIE_PATH = "/"
COOKIE_SAMESITE: Literal["lax", "strict", "none"] | None = "lax"
