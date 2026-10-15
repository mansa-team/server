"""Tests for main/utils/http_session.py — covers all branches."""

import threading
import pytest
import requests
from unittest.mock import patch, MagicMock
from main.utils.http_session import getSession


class TestGetSession:
    def test_returns_same_session(self):

        s1 = getSession()
        s2 = getSession()
        assert s1 is s2

    def test_returns_requests_session(self):
        s = getSession()
        assert isinstance(s, requests.Session)


class TestRetryPolicy:
    """Transport retries: GET-only, 5xx retried, 429 never (wallet quota semantics)."""

    def test_retries_mounted_for_http_and_https(self):
        session = getSession()
        for prefix in ("http://", "https://"):
            retries = session.get_adapter(prefix).max_retries
            assert retries.total == 2
            assert retries.backoff_factor == 0.5
            assert set(retries.status_forcelist) == {500, 502, 503, 504}
            assert set(retries.allowed_methods) == {"GET"}
            assert retries.raise_on_status is False

    def test_429_not_retried(self):
        retries = getSession().get_adapter("http://x").max_retries
        assert 429 not in retries.status_forcelist
