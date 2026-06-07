import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock
from fastapi import HTTPException, Request


class TestExtractTokenPayload:
    """Tests for extractTokenPayload — the standalone token extraction dependency."""

    def _make_request(self, headers: dict) -> Request:
        """Create a mock Starlette Request with given headers."""
        scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
        return Request(scope)

    def test_missing_token_raises_401(self):
        from main.app.authentication.util import extractTokenPayload

        request = self._make_request({})
        with pytest.raises(HTTPException) as exc_info:
            extractTokenPayload(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Session not found"

    def test_x_access_token_header_used(self):
        from main.app.authentication.util import extractTokenPayload

        mock_payload = {"userId": 1, "sessionId": "abc"}
        request = self._make_request({"X-Access-Token": "valid_token"})

        with patch("main.app.authentication.util.verifyAccessToken", return_value=mock_payload):
            result = extractTokenPayload(request)
            assert result == mock_payload

    def test_authorization_bearer_header_used(self):
        from main.app.authentication.util import extractTokenPayload

        mock_payload = {"userId": 2}
        request = self._make_request({"Authorization": "Bearer my_jwt_token"})

        with patch("main.app.authentication.util.verifyAccessToken", return_value=mock_payload):
            result = extractTokenPayload(request)
            assert result == mock_payload

    def test_x_access_token_takes_priority_over_bearer(self):
        from main.app.authentication.util import extractTokenPayload

        mock_payload = {"userId": 3}
        request = self._make_request({"X-Access-Token": "primary_token", "Authorization": "Bearer secondary_token"})

        with patch("main.app.authentication.util.verifyAccessToken", return_value=mock_payload) as mock_verify:
            result = extractTokenPayload(request)
            mock_verify.assert_called_once_with("primary_token")

    def test_invalid_token_raises_401(self):
        from main.app.authentication.util import extractTokenPayload

        request = self._make_request({"X-Access-Token": "bad_token"})
        with patch("main.app.authentication.util.verifyAccessToken", side_effect=Exception("decode error")):
            with pytest.raises(HTTPException) as exc_info:
                extractTokenPayload(request)
            assert exc_info.value.status_code == 401
            assert "Invalid Token" in exc_info.value.detail

    def test_empty_user_id_raises_401(self):
        from main.app.authentication.util import extractTokenPayload

        request = self._make_request({"X-Access-Token": "token"})
        with patch("main.app.authentication.util.verifyAccessToken", return_value={"userId": None}):
            with pytest.raises(HTTPException) as exc_info:
                extractTokenPayload(request)
            assert exc_info.value.status_code == 401

    def test_empty_bearer_value_raises_401(self):
        """Authorization: Bearer (empty) — no token after Bearer."""
        from main.app.authentication.util import extractTokenPayload

        request = self._make_request({"Authorization": "Bearer "})
        with pytest.raises(HTTPException) as exc_info:
            extractTokenPayload(request)
        assert exc_info.value.status_code == 401

    def test_non_bearer_auth_header_raises_401(self):
        """Authorization: Basic xxx — not Bearer, so no token found."""
        from main.app.authentication.util import extractTokenPayload

        request = self._make_request({"Authorization": "Basic dXNlcjpwYXNz"})
        with pytest.raises(HTTPException) as exc_info:
            extractTokenPayload(request)
        assert exc_info.value.status_code == 401
