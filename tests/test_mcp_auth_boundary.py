"""Wallet FastMCP (/wallet/mcp) auth boundary — Task 4 of the FastMCP replacement plan.

In-process Client over walletMcp: the transport-level walletAuth gate is
bypassed in-memory, so these tests pin the per-tool identity path
(verifyAccessToken + SessionManager.validateSession revocation check).
Mirrors tests/test_wallet_mcp.py TestWalletMCPAuthBoundary semantics.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cashews import cache as cashewsCache
from fastmcp import Client

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.authentication.session import SessionManager
from main.app.authentication.util import createAccessToken, walletAuth
from main.app.wallet.entries import EntriesManager, EntryCreate
from main.app.wallet.wallets import WalletsManager
from main.models.user import User
from main.controller.wallet_controller import mcp as walletMcp
from tests.test_wallet_positions import _live_ok


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _seed_session_user(dbSession, username="mcpuser"):
    """Real user + active session row (production auth chain)."""
    user = User(username=username, email=f"{username}@example.com", passwordHash="hash", roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    session = SessionManager.createSession(dbSession, user.userId, "pytest")
    return user, session


def _seed_session_token(dbSession, username="mcpuser"):
    """Signed session JWT for a freshly seeded user+session (production auth chain)."""
    user, session = _seed_session_user(dbSession, username)
    return createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})


def _seed_session_wallet(dbSession, ticker="PETR4", quantity=10, price=10.0):
    """Authed user (session JWT) + wallet + one ledger entry. Returns the token."""
    token = _seed_session_token(dbSession)
    user = dbSession.query(User).filter(User.username == "mcpuser").one()
    wallet = WalletsManager.getMyWallet(dbSession, user.userId)
    EntriesManager.addEntry(
        dbSession,
        wallet,
        EntryCreate(
            side="Compra",
            asset_type="ACOES",
            ticker=ticker,
            date=date(2026, 1, 2),
            quantity=quantity,
            price=price,
        ),
    )
    return token


def _use_test_db(monkeypatch, dbSession):
    """Route tool bodies at the sqlite fixture instead of the production session."""
    monkeypatch.setattr("main.controller.wallet_controller.SessionLocal", lambda: dbSession)
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))


async def test_mcp_without_token_rejected(dbSession, monkeypatch):
    _use_test_db(monkeypatch, dbSession)
    assert walletAuth is not None
    async with Client(walletMcp) as client:
        result = await client.call_tool("wallet_positions", {}, raise_on_error=False)
    assert result.is_error
    assert "401" in result.content[0].text


async def test_mcp_with_valid_session_jwt_succeeds(dbSession, monkeypatch):
    _use_test_db(monkeypatch, dbSession)
    token = _seed_session_token(dbSession)
    async with Client(walletMcp) as client:
        result = await client.call_tool("wallet_positions", {"authorization": f"Bearer {token}"}, raise_on_error=False)
    assert not result.is_error
    assert json.loads(result.content[0].text) == {"items": [], "equity_total": 0.0}


async def test_mcp_expired_revoked_forged_rejected(dbSession, monkeypatch):
    _use_test_db(monkeypatch, dbSession)
    user, session = _seed_session_user(dbSession, username="expireduser")
    expired = createAccessToken(
        {"userId": str(user.userId), "sessionId": session.sessionId}, expiresDelta=timedelta(seconds=-60)
    )
    revokedUser, revokedSession = _seed_session_user(dbSession, username="revokeduser")
    revokedUserId, revokedSessionId = int(revokedUser.userId), revokedSession.sessionId
    revokedToken = createAccessToken({"userId": str(revokedUserId), "sessionId": revokedSessionId})
    assert SessionManager.revokeSession(dbSession, revokedSessionId, revokedUserId)
    forged = jwt.encode(
        {"userId": "1", "sessionId": "forged-session", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "wrong-secret-not-the-real-signing-key",
        algorithm="HS256",
    )
    async with Client(walletMcp) as client:
        for bad in (expired, revokedToken, forged):
            result = await client.call_tool(
                "wallet_positions", {"authorization": f"Bearer {bad}"}, raise_on_error=False
            )
            assert result.is_error
            assert "401" in result.content[0].text


async def test_mcp_cross_user_isolation(dbSession, monkeypatch):
    """A's token sees A's PETR4 ledger; B's token sees B's own empty wallet."""
    _use_test_db(monkeypatch, dbSession)
    tokenA = _seed_session_wallet(dbSession)
    tokenB = _seed_session_token(dbSession, username="otheruser")
    async with Client(walletMcp) as client:
        positionsA = await client.call_tool(
            "wallet_positions", {"authorization": f"Bearer {tokenA}"}, raise_on_error=False
        )
        summaryA = await client.call_tool("wallet_summary", {"authorization": f"Bearer {tokenA}"}, raise_on_error=False)
        positionsB = await client.call_tool(
            "wallet_positions", {"authorization": f"Bearer {tokenB}"}, raise_on_error=False
        )
        summaryB = await client.call_tool("wallet_summary", {"authorization": f"Bearer {tokenB}"}, raise_on_error=False)
    payloadA = json.loads(positionsA.content[0].text)
    assert [item["ticker"] for item in payloadA["items"]] == ["PETR4"]
    assert payloadA["equity_total"] == 300.0
    summaryPayloadA = json.loads(summaryA.content[0].text)
    assert summaryPayloadA["applied"] == 100.0
    assert summaryPayloadA["first_date"] == "2026-01-02"
    payloadB = json.loads(positionsB.content[0].text)
    assert payloadB == {"items": [], "equity_total": 0.0}
    summaryPayloadB = json.loads(summaryB.content[0].text)
    assert summaryPayloadB["applied"] == 0.0
    assert summaryPayloadB["first_date"] is None
    assert "PETR4" not in positionsB.content[0].text
    assert "PETR4" not in summaryB.content[0].text


async def test_mcp_service_token_never_resolves_user(dbSession, monkeypatch):
    """R2: an opaque service token as the per-tool identity arg still 401s."""
    _use_test_db(monkeypatch, dbSession)
    async with Client(walletMcp) as client:
        result = await client.call_tool(
            "wallet_positions", {"authorization": "Bearer opaque-service-session-uuid"}, raise_on_error=False
        )
    assert result.is_error
    assert "401" in result.content[0].text
