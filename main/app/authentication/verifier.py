import logging

from authlib.oauth2.rfc9068.token_validator import JWTBearerTokenValidator
from fastapi import HTTPException
from joserfc.jwk import OctKey
from sqlalchemy.orm import Session

from config import Config
from main.app.authentication.constants import ISSUER, WALLET_RESOURCE_PATH
from main.app.authentication.session import SessionManager
from main.app.authentication.tokens import decodeToken, rawClaims
from main.models.user import User, getRolesList

logger = logging.getLogger(__name__)

REVOKED_ACCESS_JTIS: set[str] = set()


def resourceUrl() -> str:
    return f"{Config.USER.MCP_PUBLIC_BASE_URL.rstrip('/')}{WALLET_RESOURCE_PATH}"


class MansaJWTValidator(JWTBearerTokenValidator):
    def __init__(self) -> None:
        super().__init__(ISSUER, resourceUrl())

    def get_jwks(self):  # type: ignore[no-untyped-def]
        return OctKey.import_key(Config.USER.JWT_SECRET_KEY)


oauthTokenValidator = MansaJWTValidator()


def verifyAccessTokenClaims(token: str, db: Session) -> dict | None:
    raw = rawClaims(token)
    if str(raw.get("jti") or "") in REVOKED_ACCESS_JTIS:
        return None

    claims: dict | None = None
    if raw.get("iss"):
        try:
            claims = dict(oauthTokenValidator.authenticate_token(token))
        except Exception:
            claims = None
    if claims is None:
        try:
            claims = decodeToken(token)
        except Exception:
            claims = None
    if claims is None:
        return None

    userId = claims.get("userId") or claims.get("sub")
    sessionId = claims.get("sessionId")
    if userId is None or not sessionId:
        return None
    try:
        userIdInt = int(userId)
    except (TypeError, ValueError):
        return None

    user = db.query(User).filter(User.userId == userIdInt).first()
    if user is None:
        return None
    roles = (getattr(user, "roles", "") or "").lower()
    if getattr(user, "username", "") == "service-loopback" or "service" in roles:
        return None
    if not SessionManager.validateSession(db, str(sessionId), userIdInt):
        return None
    return claims


def resolveSessionIdentity(db: Session, token: str) -> tuple[int, str] | None:
    try:
        claims = verifyAccessTokenClaims(token, db)
    except Exception:
        return None
    if not claims:
        return None
    userIdRaw = claims.get("userId") or claims.get("sub")
    sessionId = claims.get("sessionId")
    if userIdRaw is None or not sessionId:
        return None
    try:
        userId = int(userIdRaw)
    except (TypeError, ValueError):
        return None
    return userId, str(sessionId)


def introspectToken(db: Session, token: str | None) -> dict:
    try:
        raw = (token or "").strip().removeprefix("Bearer ").strip()
        if not raw:
            raise HTTPException(status_code=401, detail="Unauthorized")

        identity = resolveSessionIdentity(db, raw)
        if identity is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = db.query(User).filter(User.userId == identity[0]).first()
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        return {"userId": user.userId, "username": user.username, "roles": getRolesList(user)}
    except HTTPException:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as e:
        logger.warning(f"Token introspection failed: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")
