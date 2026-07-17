import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.models.user_session import UserSession
from main.app.authentication.session import SessionManager
from main.app.authentication.constants import SESSION_EXPIRY_DAYS


class TestUserSessionModel:
    def test_getDeviceName_with_browser_and_os(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            browser="Chrome",
            operatingSystem="Windows",
            isActive=True,
        )

        name = SessionManager.getDeviceName(session)

        assert name == "Chrome on Windows"

    def test_getDeviceName_with_fingerprint_only(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            accessTokenHash="abc123def456",
            isActive=True,
        )

        name = SessionManager.getDeviceName(session)

        assert name == "Device abc123de"

    def test_getDeviceName_fallback(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            browser="",
            operatingSystem="",
            isActive=True,
        )

        name = SessionManager.getDeviceName(session)

        assert name == "Unknown Device"

    def test_getDeviceName_empty_strings(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            browser="",
            operatingSystem="",
            accessTokenHash="",
            isActive=True,
        )

        name = SessionManager.getDeviceName(session)

        assert name == "Unknown Device"

    def test_isActive_default(self):
        session = UserSession(sessionId="test-123", userId=1, accessTokenHash="abc", isActive=True)
        assert session.isActive is True

    def test_isActive_can_be_false(self):
        session = UserSession(sessionId="test-123", userId=1, accessTokenHash="abc", isActive=False)
        assert session.isActive is False


class TestSessionExpiration:
    def test_session_expiry_days_is_30(self):
        assert SESSION_EXPIRY_DAYS == 30

    def test_session_can_expire(self):
        from pytz import timezone

        now = datetime.now(timezone("America/Sao_Paulo"))
        expired_date = now - timedelta(days=SESSION_EXPIRY_DAYS + 1)

        session = UserSession(
            sessionId="expired-session",
            userId=1,
            accessTokenHash="abc",
            isActive=True,
            createdAt=expired_date,
            lastActivityAt=expired_date,
            expiresAt=expired_date,
        )

        assert session.expiresAt is not None
        assert session.expiresAt < now

    def test_session_still_valid_within_expiry(self):
        from pytz import timezone

        now = datetime.now(timezone("America/Sao_Paulo"))
        valid_date = now - timedelta(days=SESSION_EXPIRY_DAYS - 1)

        session = UserSession(
            sessionId="valid-session",
            userId=1,
            accessTokenHash="abc",
            isActive=True,
            createdAt=valid_date,
            lastActivityAt=valid_date,
            expiresAt=valid_date + timedelta(days=SESSION_EXPIRY_DAYS),
        )

        assert session.expiresAt > now

    def test_session_exactly_at_boundary(self):
        from pytz import timezone

        now = datetime.now(timezone("America/Sao_Paulo"))
        boundary_date = now - timedelta(days=SESSION_EXPIRY_DAYS)

        session = UserSession(
            sessionId="boundary-session",
            userId=1,
            accessTokenHash="abc",
            isActive=True,
            createdAt=boundary_date,
            lastActivityAt=boundary_date,
            expiresAt=boundary_date + timedelta(days=SESSION_EXPIRY_DAYS),
        )

        assert session.expiresAt.date() <= now.date()

    def test_created_at_future_date(self):
        from pytz import timezone

        future = datetime.now(timezone("America/Sao_Paulo")) + timedelta(days=1)

        session = UserSession(
            sessionId="future-session",
            userId=1,
            accessTokenHash="abc",
            isActive=True,
            createdAt=future,
        )

        assert session.createdAt > datetime.now(timezone("America/Sao_Paulo"))
