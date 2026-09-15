import pytest
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from freezegun import freeze_time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.models.user_session import UserSession
from main.app.authentication.session import SessionManager
from main.app.authentication.constants import SESSION_EXPIRY_DAYS


class TestUserSessionModel:
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
        now = datetime.now()
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
        now = datetime.now()
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
        now = datetime.now()
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
        future = datetime.now() + timedelta(days=1)

        session = UserSession(
            sessionId="future-session",
            userId=1,
            accessTokenHash="abc",
            isActive=True,
            createdAt=future,
        )

        assert session.createdAt > datetime.now()


# ---- moved from test_prometheus_auth_coverage.py (TestSessionManager) ----


class TestSessionManager:
    """Cover all methods in session.py (lines 14-154)."""

    @freeze_time("2026-03-23 12:00:00")
    def test_create_session(self, mocker):
        from main.app.authentication.session import SessionManager

        mocker.patch(
            "main.app.authentication.session.secrets.token_urlsafe",
            return_value="session-id-123",
        )
        mocker.patch(
            "main.app.authentication.session.secrets.token_hex",
            return_value="a" * 64,
        )

        mock_db = MagicMock()

        result = SessionManager.createSession(mock_db, userId=1, userAgent="Mozilla/5.0")

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result.sessionId == "session-id-123"

    @freeze_time("2026-03-23 12:00:00")
    def test_create_session_custom_expiry(self, mocker):
        from main.app.authentication.session import SessionManager

        mocker.patch(
            "main.app.authentication.session.secrets.token_urlsafe",
            return_value="session-id-456",
        )
        mocker.patch(
            "main.app.authentication.session.secrets.token_hex",
            return_value="b" * 64,
        )

        mock_now = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
        custom_expiry = mock_now + timedelta(days=7)
        mock_db = MagicMock()

        result = SessionManager.createSession(mock_db, userId=2, userAgent="Safari", expiresAt=custom_expiry)
        assert result.expiresAt == custom_expiry

    def test_get_user_sessions_active_only(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        SessionManager.getUserSessions(mock_db, userId=1)

        query = mock_db.query.return_value.filter.return_value
        # Single .filter(userId, isActive).order_by().limit().all()
        query.order_by.return_value.limit.return_value.all.assert_called_once()

    def test_get_session_by_id(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        SessionManager.getSessionById(mock_db, "sess-123", userId=1)

        query_filter = mock_db.query.return_value.filter.return_value
        query_filter.filter.return_value.first.assert_called_once()

    def test_get_session_by_id_no_user_id(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        SessionManager.getSessionById(mock_db, "sess-123")

        # With no userId, only one filter is applied
        mock_db.query.return_value.filter.return_value.first.assert_called_once()

    def test_get_current_session(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        result = SessionManager.getCurrentSession(mock_db, userId=1)

        mock_db.query.return_value.filter.return_value.order_by.return_value.first.assert_called_once()

    def test_revoke_session_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.revokeSession(mock_db, "sess-123", userId=1)
        assert result is True
        assert mock_session.isActive is False
        mock_db.commit.assert_called_once()

    def test_revoke_session_not_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

        result = SessionManager.revokeSession(mock_db, "nonexistent", userId=1)
        assert result is False

    def test_revoke_all_sessions(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        # revokeAllSessions: db.query(...).filter(userId, isActive).update(...)
        mock_db.query.return_value.filter.return_value.update.return_value = 5

        count = SessionManager.revokeAllSessions(mock_db, userId=1)
        assert count == 5
        mock_db.commit.assert_called_once()

    def test_update_last_active_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.updateLastActive(mock_db, "sess-123")
        assert result is True
        mock_db.commit.assert_called_once()

    def test_update_last_active_not_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = SessionManager.updateLastActive(mock_db, "nonexistent")
        assert result is False

    def test_validate_session_active(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        mock_session.expiresAt = datetime(2026, 12, 31, tzinfo=ZoneInfo("America/Sao_Paulo"))
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is True

    def test_validate_session_not_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

        result = SessionManager.validateSession(mock_db, "nonexistent", userId=1)
        assert result is False

    def test_validate_session_inactive(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = False
        mock_session.expiresAt = datetime(2026, 12, 31, tzinfo=ZoneInfo("America/Sao_Paulo"))
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is False

    def test_validate_session_expired(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        mock_session.expiresAt = datetime(2020, 1, 1, tzinfo=ZoneInfo("America/Sao_Paulo"))
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is False
        assert mock_session.isActive is False
        mock_db.commit.assert_called_once()

    def test_validate_session_expired_naive_tz(self):
        """Exercises the tzinfo-is-None branch (line 144-148)."""
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        # Naive datetime (no timezone)
        mock_session.expiresAt = datetime(2020, 1, 1)
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is False

    def test_validate_session_no_expiry(self):
        """Exercises the expiresAt-is-None branch (line 143)."""
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        mock_session.expiresAt = None
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is True


# ---------------------------------------------------------------------------
# SSO (sso.py)
# ---------------------------------------------------------------------------
