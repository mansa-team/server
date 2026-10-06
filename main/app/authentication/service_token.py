"""Independent expiring/rotatable service token for POST /auth/introspect.

Replaces the old static HMAC(JWT_SECRET_KEY, b"auth-introspect") which leaked
the user-secret into the service credential and never expired.

Format: HS256 JWT {"typ": "service", "exp": ...} signed with an independent
secret (INTROSPECT_SERVICE_SECRET). Rotation: set PREV to the old secret,
SECRET to the new one, re-mint, then drop PREV after TTL.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import jwt

from config import Config

logger = logging.getLogger(__name__)

SERVICE_TYP = "service"


def _secrets() -> tuple[str, str]:
    return (Config.USER.SERVICE_TOKEN_SECRET or "", Config.USER.SERVICE_TOKEN_SECRET_PREV or "")


def createServiceToken(expiresDelta: timedelta | None = None) -> str:
    secret, _ = _secrets()
    if not secret:
        raise ValueError("INTROSPECT_SERVICE_SECRET is not configured")
    if expiresDelta is None:
        expiresDelta = timedelta(hours=Config.USER.SERVICE_TOKEN_TTL_HOURS)
    payload = {"typ": SERVICE_TYP, "exp": datetime.now(timezone.utc) + expiresDelta}
    return jwt.encode(payload, secret, algorithm="HS256")


def _verifyWithSecret(token: str, secret: str) -> bool:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return False
    return payload.get("typ") == SERVICE_TYP


def verifyServiceToken(provided: str) -> bool:
    token = (provided or "").strip()
    if not token:
        return False
    secret, prev = _secrets()
    # Independent-secret path (preferred once configured).
    if secret or prev:
        if secret and _verifyWithSecret(token, secret):
            return True
        if prev and _verifyWithSecret(token, prev):
            return True
        return False
    # Migration fallback: legacy static HMAC derived from JWT_SECRET_KEY.
    # Disabled as soon as either service secret is configured.
    try:
        expected = hmac.new(Config.USER.JWT_SECRET_KEY.encode("utf-8"), b"auth-introspect", hashlib.sha256).hexdigest()
    except Exception:
        return False
    return bool(expected) and hmac.compare_digest(token, expected)
