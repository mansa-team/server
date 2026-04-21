import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.models.user_session import UserSession


class TestUserSessionModel:
    def test_repr(self):
        session = UserSession(sessionId="test-123", userId=1, isActive=True)
        assert "test-123" in repr(session)
        assert "1" in repr(session)

    def test_to_dict_basic(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            browser="Chrome",
            operatingSystem="Windows",
            deviceType="desktop",
            isActive=True,
        )
        result = session.toDict()

        assert result["sessionId"] == "test-123"
        assert result["browser"] == "Chrome"
        assert result["os"] == "Windows"
        assert result["deviceType"] == "desktop"
        assert result["isActive"] is True

    def test_to_dict_with_sensitive(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            userAgent="Mozilla/5.0",
            isActive=True,
        )
        result = session.toDict(includeSensitive=True)

        assert result["userAgent"] == "Mozilla/5.0"

    def test_to_dict_hides_userAgent(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            userAgent="Mozilla/5.0",
            isActive=True,
        )
        result = session.toDict()

        assert result["userAgent"] is None

    def test_getDeviceName_with_browser_and_os(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            browser="Chrome",
            operatingSystem="Windows",
            isActive=True,
        )

        name = session.getDeviceName()

        assert name == "Chrome on Windows"

    def test_getDeviceName_with_fingerprint_only(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            accessTokenHash="abc123def456",
            isActive=True,
        )

        name = session.getDeviceName()

        assert name == "Device abc123de"

    def test_getDeviceName_fallback(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            browser="",
            operatingSystem="",
            isActive=True,
        )

        name = session.getDeviceName()

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

        name = session.getDeviceName()

        assert name == "Unknown Device"

    def test_isActive_default(self):
        session = UserSession(sessionId="test-123", userId=1, accessTokenHash="abc", isActive=True)
        assert session.isActive is True

    def test_isActive_can_be_false(self):
        session = UserSession(sessionId="test-123", userId=1, accessTokenHash="abc", isActive=False)
        assert session.isActive is False

    def test_toDict_with_timestamps(self):
        from datetime import datetime

        session = UserSession(
            sessionId="test-123",
            userId=1,
            accessTokenHash="abc",
            createdAt=datetime(2026, 4, 21),
            lastActivityAt=datetime(2026, 4, 21, 12, 0, 0),
            isActive=True,
        )
        result = session.toDict()

        assert "2026-04-21" in result["createdAt"]
        assert "2026-04-21" in result["lastActiveAt"]

    def test_toDict_without_timestamps(self):
        session = UserSession(
            sessionId="test-123",
            userId=1,
            accessTokenHash="abc",
            isActive=True,
        )
        result = session.toDict()

        assert result["createdAt"] is None
        assert result["lastActiveAt"] is None
