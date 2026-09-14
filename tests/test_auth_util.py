import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.authentication.util import hashPassword, verifyPassword, createAccessToken
from main.app.authentication.constants import SESSION_EXPIRY_DAYS
from datetime import timedelta, datetime
from unittest.mock import MagicMock, patch

import jwt


class TestAuthUtil:
    def test_hash_password_returns_string(self):
        result = hashPassword("testpassword123")
        assert isinstance(result, str)
        assert result != "testpassword123"

    def test_hash_password_unique_hashes(self):
        password = "samepassword"
        hash1 = hashPassword(password)
        hash2 = hashPassword(password)
        assert hash1 != hash2

    def test_verify_password_correct(self):
        password = "testpassword123"
        hashed = hashPassword(password)
        assert verifyPassword(password, hashed) is True

    def test_verify_password_incorrect(self):
        password = "testpassword123"
        hashed = hashPassword(password)
        assert verifyPassword("wrongpassword", hashed) is False

    def test_verify_password_invalid_hash(self):
        assert verifyPassword("anypassword", "invalid_hash") is False

    def test_verify_password_empty_password(self):
        hashed = hashPassword("password")
        assert verifyPassword("", hashed) is False

    def test_create_access_token_default_expiry(self):
        token = createAccessToken({"userId": "123"})
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert "exp" in decoded
        assert decoded["userId"] == "123"

    def test_create_access_token_custom_expiry(self):
        customDelta = timedelta(hours=48)
        token = createAccessToken({"userId": "123"}, expiresDelta=customDelta)
        decoded = jwt.decode(token, options={"verify_signature": False})

        expTime = datetime.fromtimestamp(decoded["exp"])
        now = datetime.now()
        hoursDiff = (expTime - now).total_seconds() / 3600

        assert 44 <= hoursDiff <= 49

    def test_create_access_token_contains_data(self):
        data = {"userId": "456", "username": "testuser"}
        token = createAccessToken(data)
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert decoded["userId"] == "456"


class TestSessionExpiryConfig:
    def test_session_expiry_days_is_30(self):
        assert SESSION_EXPIRY_DAYS == 30

    def test_session_expiry_hours_calculation(self):
        from main.app.authentication.constants import TOKEN_EXPIRY_HOURS

        assert TOKEN_EXPIRY_HOURS == SESSION_EXPIRY_DAYS * 24

    def test_default_token_expiry_equals_30_days(self):
        token = createAccessToken({"userId": "123"})
        decoded = jwt.decode(token, options={"verify_signature": False})

        expTime = datetime.fromtimestamp(decoded["exp"])
        now = datetime.now()
        daysDiff = (expTime - now).days

        assert 29 <= daysDiff <= 30


class TestAuthUtilEdgeCases:
    def test_verify_password_none_hash(self):
        result = verifyPassword("password", None)
        assert result is False

    def test_verify_password_none_password(self):
        hashed = hashPassword("password")
        result = verifyPassword(None, hashed)
        assert result is False

    def test_verify_password_both_none(self):
        result = verifyPassword(None, None)
        assert result is False

    def test_create_access_token_with_empty_data(self):
        token = createAccessToken({})
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert "exp" in decoded

    def test_create_access_token_with_none_data(self):
        token = createAccessToken(None)
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert "exp" in decoded


# ---- moved from test_prometheus_auth_coverage.py (TestAuthenticationManager) ----


class TestAuthenticationManager:
    """Cover all methods in authentication.py (lines 13-75)."""

    @patch("main.app.authentication.authentication.hashPassword")
    def test_create_user_account_success(self, mock_hash):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_hash.return_value = "hashed_pw"

        result = AuthenticationManager.createUserAccount(mock_db, "newuser", "new@example.com", password="pass123")
        assert result is True
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_create_user_account_no_password_no_google(self):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "user", "e@e.com")
        assert exc_info.value.status_code == 400
        assert "password" in exc_info.value.detail.lower()

    def test_create_user_account_username_taken(self):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()
        existing = MagicMock()
        existing.username = "taken"
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "taken", "e@e.com", password="pass")
        assert exc_info.value.status_code == 400
        assert "Username already taken" in exc_info.value.detail

    def test_create_user_account_email_taken(self):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()
        existing = MagicMock()
        existing.username = "other"
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "newuser", "taken@example.com", password="pass")
        assert exc_info.value.status_code == 400
        assert "Email already registered" in exc_info.value.detail

    @patch("main.app.authentication.authentication.hashPassword")
    def test_create_user_account_db_exception(self, mock_hash):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit.side_effect = Exception("DB error")
        mock_hash.return_value = "hashed"

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "user", "e@e.com", password="pass")
        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called()

    def test_create_user_account_with_google_id(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AuthenticationManager.createUserAccount(mock_db, "googleuser", "g@g.com", googleId="google-123")
        assert result is True

    def test_authenticate_google_user_found(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.userId = 1
        mock_user.username = "testuser"
        mock_user.getRolesList.return_value = ["USER"]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = AuthenticationManager.authenticateGoogleUser(mock_db, "google-123")
        assert result is not None
        assert result["userId"] == 1
        assert result["username"] == "testuser"

    def test_authenticate_google_user_not_found(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AuthenticationManager.authenticateGoogleUser(mock_db, "nonexistent")
        assert result is None

    def test_authenticate_google_user_exception(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        result = AuthenticationManager.authenticateGoogleUser(mock_db, "google-123")
        assert result is None

    @patch("main.app.authentication.authentication.verifyPassword")
    def test_authenticate_user_success(self, mock_verify):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.userId = 1
        mock_user.username = "testuser"
        mock_user.passwordHash = "hashed"
        mock_user.getRolesList.return_value = ["USER"]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_verify.return_value = True

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "pass123")
        assert result is not None
        assert result["userId"] == 1

    @patch("main.app.authentication.authentication.verifyPassword")
    def test_authenticate_user_wrong_password(self, mock_verify):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.passwordHash = "hashed"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_verify.return_value = False

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "wrong")
        assert result is None

    def test_authenticate_user_not_found(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AuthenticationManager.authenticateUser(mock_db, "nobody", "pass")
        assert result is None

    def test_authenticate_user_no_password_hash(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.passwordHash = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "pass")
        assert result is None

    def test_authenticate_user_exception(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "pass")
        assert result is None


# ---------------------------------------------------------------------------
# SessionManager (session.py)
# ---------------------------------------------------------------------------
