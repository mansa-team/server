"""Tests for main/utils/http_session.py — covers all branches."""

import threading
import pytest
from unittest.mock import patch, MagicMock


class TestGetSession:
    def test_returns_same_session(self):
        from main.utils.http_session import getSession

        s1 = getSession()
        s2 = getSession()
        assert s1 is s2

    def test_returns_requests_session(self):
        import requests
        from main.utils.http_session import getSession

        s = getSession()
        assert isinstance(s, requests.Session)


class TestCleanup:
    def test_cleanup_closes_session(self):
        from main.utils.http_session import getSession, cleanup, local

        session = getSession()
        with patch.object(session, "close") as mockClose:
            cleanup()
            mockClose.assert_called_once()

    def test_cleanup_no_session(self):
        from main.utils.http_session import cleanup, local

        # Remove session from local
        if hasattr(local, "session"):
            delattr(local, "session")
        # Should not raise
        cleanup()

    def test_cleanup_exception_during_close(self):
        from main.utils.http_session import getSession, cleanup, local

        session = getSession()
        with patch.object(session, "close", side_effect=RuntimeError("close failed")):
            # Should not raise
            cleanup()
