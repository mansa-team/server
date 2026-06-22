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
