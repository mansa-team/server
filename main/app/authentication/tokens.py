import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import HTTPException
from joserfc import jwt
from joserfc.errors import ExpiredTokenError, JoseError
from joserfc.jwk import OctKey

from config import Config
from main.app.authentication.constants import TOKEN_EXPIRY_HOURS

claimsRegistry = jwt.JWTClaimsRegistry()
logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"


@lru_cache(maxsize=4)
def signingKey() -> OctKey:
    return OctKey.import_key(Config.AUTH.JWT_SECRET_KEY)


def mintToken(
    data: dict | None,
    expiresDelta: timedelta | None = None,
    *,
    issuer: str | None = None,
    audience: str | list[str] | None = None,
    scope: str | None = None,
) -> str:
    if data is None:
        data = {}
    if expiresDelta is None:
        expiresDelta = timedelta(hours=TOKEN_EXPIRY_HOURS)

    claims = dict(data)
    claims["exp"] = int((datetime.now(timezone.utc) + expiresDelta).timestamp())
    if issuer is not None:
        claims["iss"] = issuer
    if audience is not None:
        claims["aud"] = audience
    if scope is not None:
        claims["scope"] = scope

    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    return jwt.encode(header, claims, key=signingKey())


def decodeToken(token: str) -> dict:
    try:
        claims = dict(jwt.decode(token, key=signingKey(), algorithms=[JWT_ALGORITHM]).claims)
        claimsRegistry.validate(claims)
        return claims
    except ExpiredTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JoseError:
        raise HTTPException(status_code=401, detail="Invalid token")


def rawClaims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))


createAccessToken = mintToken
verifyAccessToken = decodeToken
