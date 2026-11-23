"""Contract tests for the Authlib-based auth foundation.

These pin what other components rely on: HS256 token mint/verify with expiry,
RFC 9068 claims from the Authlib grant engine, PKCE S256, refresh rotation,
revocation by jti, service-loopback tokens never being an identity, and
session-backed introspection.  No new DB tables are involved.
"""

import os
import sys
from datetime import timedelta

import pytest
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config  # noqa: E402
from main.app.authentication.constants import ISSUER  # noqa: E402
from main.app.authentication.mcp.server import (  # noqa: E402
    MansaAuthorizationServer,
    OAuthStore,
    OAuthUser,
    StaticClient,
)
from main.app.authentication.mcp.verifier import verifyMcpAccessToken  # noqa: E402
from main.app.authentication.verifier import (  # noqa: E402
    REVOKED_ACCESS_JTIS,
    verifyWalletUser,
    oauthTokenValidator,
    resourceUrl,
    verifyAccessTokenClaims,
)
from main.app.authentication.service_token import createServiceToken, getServiceUserId  # noqa: E402
from main.app.authentication.session import SessionManager  # noqa: E402
from main.app.authentication.tokens import createAccessToken, decodeToken, rawClaims  # noqa: E402
from main.models.user import User  # noqa: E402


@pytest.fixture(autouse=True)
def clearRevokedJtis():
    REVOKED_ACCESS_JTIS.clear()
    yield
    REVOKED_ACCESS_JTIS.clear()


def makeUserAndSession(dbSession, username="contract_user"):
    user = User(username=username, email=f"{username}@example.com", passwordHash="hashed", roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    session = SessionManager.createSession(dbSession, user.userId, "pytest")
    return user, session


def issueOAuthToken(dbSession, userId, sessionId):
    server = MansaAuthorizationServer(OAuthStore())
    client = StaticClient("opencode", "contract-secret", [resourceUrl()])
    return server.generate_token(
        "authorization_code",
        client,
        user=OAuthUser(userId=str(userId), sessionId=str(sessionId)),
        scope="wallet",
    )


class TestTokenMintVerify:
    def test_roundtrip_carries_claims(self):
        token = createAccessToken({"userId": "42", "sessionId": "s-42"})
        claims = decodeToken(token)
        assert claims["userId"] == "42"
        assert claims["sessionId"] == "s-42"
        assert isinstance(claims["exp"], int)

    def test_expired_token_is_401(self):
        token = createAccessToken({"userId": "1"}, expiresDelta=timedelta(hours=-1))
        with pytest.raises(HTTPException) as exc:
            decodeToken(token)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    def test_garbage_token_is_401(self):
        with pytest.raises(HTTPException) as exc:
            decodeToken("not-a-jwt")
        assert exc.value.status_code == 401


class TestAuthlibGrantEngine:
    def test_rfc9068_access_token_claims(self, dbSession):
        user, session = makeUserAndSession(dbSession)
        token = issueOAuthToken(dbSession, user.userId, session.sessionId)

        assert token["token_type"] == "Bearer"
        claims = oauthTokenValidator.authenticate_token(token["access_token"])
        assert claims["iss"] == ISSUER
        assert claims["aud"] == resourceUrl()
        assert claims["sub"] == str(user.userId)
        assert claims["client_id"] == "opencode"
        assert claims["scope"] == "wallet"
        assert claims["userId"] == str(user.userId)
        assert claims["sessionId"] == session.sessionId
        assert claims["jti"]

    def test_requested_resource_becomes_audience(self, dbSession):
        user, session = makeUserAndSession(dbSession)
        requested = "https://resource.example/wallet/mcp"
        client = StaticClient("opencode", "contract-secret", [resourceUrl()], resource=requested)
        token = MansaAuthorizationServer(OAuthStore()).generate_token(
            "authorization_code",
            client,
            user=OAuthUser(userId=str(user.userId), sessionId=session.sessionId),
            scope="wallet",
        )
        assert rawClaims(token["access_token"])["aud"] == requested

    def test_refresh_grant_accepts_both_client_auth_methods(self):
        from main.app.authentication.mcp.server import MansaRefreshTokenGrant

        assert set(MansaRefreshTokenGrant.TOKEN_ENDPOINT_AUTH_METHODS) == {
            "client_secret_basic",
            "client_secret_post",
        }
        # A refresh credential is bound to its issuing client.
        client = StaticClient("opencode", "contract-secret", [resourceUrl()])
        otherClient = StaticClient("other", "other-secret", [resourceUrl()])
        from main.app.authentication.mcp.server import RefreshRecord

        record = RefreshRecord(token="rt", clientId="opencode", scope="wallet", sessionId="s7", userId="7")
        assert record.check_client(client) is True
        assert record.check_client(otherClient) is False

    def test_pkce_s256(self):
        verifier = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
        challenge = create_s256_code_challenge(verifier)
        assert len(challenge) == 43
        assert challenge != verifier


class TestVerificationContracts:
    def test_verified_claims_bound_to_live_session(self, dbSession):
        user, session = makeUserAndSession(dbSession)
        token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})
        claims = verifyAccessTokenClaims(token, dbSession)
        assert claims is not None
        assert claims["userId"] == str(user.userId)

    def test_revoked_jti_kills_access(self, dbSession):
        user, session = makeUserAndSession(dbSession)
        token = issueOAuthToken(dbSession, user.userId, session.sessionId)["access_token"]
        assert verifyAccessTokenClaims(token, dbSession) is not None
        REVOKED_ACCESS_JTIS.add(str(rawClaims(token)["jti"]))
        assert verifyAccessTokenClaims(token, dbSession) is None

    def test_service_token_never_an_identity(self, dbSession):
        serviceUserId = getServiceUserId(dbSession)
        serviceToken = createServiceToken(dbSession)
        forged = createAccessToken({"userId": str(serviceUserId), "sessionId": "svc-session"})
        assert verifyAccessTokenClaims(forged, dbSession) is None
        assert verifyMcpAccessToken(serviceToken, dbSession) is None

    def test_issuer_token_fails_closed_when_oauth_validation_raises(self, dbSession, monkeypatch):
        user, session = makeUserAndSession(dbSession)
        issuerToken = createAccessToken(
            {"userId": str(user.userId), "sessionId": session.sessionId},
            issuer=ISSUER,
            audience="https://wrong.example",
            scope="admin",
        )

        def reject(token):
            raise ValueError("oauth validation failed")

        monkeypatch.setattr(oauthTokenValidator, "authenticate_token", reject)
        assert verifyAccessTokenClaims(issuerToken, dbSession) is None
        assert verifyMcpAccessToken(issuerToken, dbSession) is None

        appToken = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})
        assert verifyAccessTokenClaims(appToken, dbSession) is not None

    def test_wallet_identity_valid_and_invalid(self, dbSession):
        user, session = makeUserAndSession(dbSession)
        token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})
        assert verifyWalletUser(dbSession, token) == {
            "userId": user.userId,
            "username": user.username,
            "roles": ["USER"],
        }
        with pytest.raises(HTTPException):
            verifyWalletUser(dbSession, "bogus")
