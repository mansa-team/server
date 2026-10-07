import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import jwt

from config import Config

logger = logging.getLogger(__name__)

SERVICE_TYP = "service"


def createServiceToken(expiresDelta: timedelta | None = None) -> str:
    secret = Config.USER.SERVICE_TOKEN_SECRET or ""
    if not secret:
        raise ValueError("INTROSPECT_SERVICE_SECRET is not configured")
    if expiresDelta is None:
        expiresDelta = timedelta(hours=Config.USER.SERVICE_TOKEN_TTL_HOURS)
    payload = {"typ": SERVICE_TYP, "exp": datetime.now(timezone.utc) + expiresDelta}
    return jwt.encode(payload, secret, algorithm="HS256")


def verifyWithSecret(token: str, secret: str) -> bool:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return False
    return payload.get("typ") == SERVICE_TYP


def verifyServiceToken(provided: str) -> bool:
    token = (provided or "").strip()
    if not token:
        return False
    secret = Config.USER.SERVICE_TOKEN_SECRET or ""
    prev = Config.USER.SERVICE_TOKEN_SECRET_PREV or ""

    if secret or prev:
        if secret and verifyWithSecret(token, secret):
            return True
        if prev and verifyWithSecret(token, prev):
            return True
        return False

    try:
        expected = hmac.new(Config.USER.JWT_SECRET_KEY.encode("utf-8"), b"auth-introspect", hashlib.sha256).hexdigest()
    except Exception:
        return False
    return bool(expected) and hmac.compare_digest(token, expected)
