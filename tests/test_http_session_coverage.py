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
