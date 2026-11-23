from __future__ import annotations

from fastmcp.server.auth import AccessToken
from sqlalchemy.orm import Session

from main.app.authentication.constants import WALLET_SCOPE
from main.app.authentication.verifier import verifyAccessTokenClaims


def verifyMcpAccessToken(token: str, db: Session) -> AccessToken | None:
    try:
        claims = verifyAccessTokenClaims(token, db)
        if claims is None:
            return None
        exp = claims.get("exp")
        resource = claims.get("aud")
        scopeRaw = claims.get("scope")
        scopes = scopeRaw.split() if isinstance(scopeRaw, str) and scopeRaw else [WALLET_SCOPE]
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id") or ""),
            scopes=scopes,
            expires_at=int(exp) if isinstance(exp, (int, float)) else None,
            resource=str(resource) if resource else None,
            subject=str(claims.get("userId") or claims.get("sub") or ""),
            claims=claims,
        )
    except Exception:
        return None
