import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.authentication.util import hashPassword, verifyPassword, createAccessToken
from main.app.authentication.constants import SESSION_EXPIRY_DAYS
from datetime import timedelta, datetime
from pytz import timezone
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
        token, _ = createAccessToken({"userId": "123"})
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert "exp" in decoded
        assert decoded["userId"] == "123"

    def test_create_access_token_custom_expiry(self):
        customDelta = timedelta(hours=48)
        token, _ = createAccessToken({"userId": "123"}, expiresDelta=customDelta)
        decoded = jwt.decode(token, options={"verify_signature": False})

        expTime = datetime.fromtimestamp(decoded["exp"], tz=timezone("America/Sao_Paulo"))
        now = datetime.now()
        hoursDiff = (expTime - now).total_seconds() / 3600

        assert 47 <= hoursDiff <= 49

    def test_create_access_token_contains_data(self):
        data = {"userId": "456", "username": "testuser"}
        token, _ = createAccessToken(data)
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert decoded["userId"] == "456"


class TestSessionExpiryConfig:
    def test_session_expiry_days_is_30(self):
        assert SESSION_EXPIRY_DAYS == 30

    def test_session_expiry_hours_calculation(self):
        from main.app.authentication.constants import TOKEN_EXPIRY_HOURS

        assert TOKEN_EXPIRY_HOURS == SESSION_EXPIRY_DAYS * 24

    def test_default_token_expiry_equals_30_days(self):
        token, _ = createAccessToken({"userId": "123"})
        decoded = jwt.decode(token, options={"verify_signature": False})

        expTime = datetime.fromtimestamp(decoded["exp"], tz=timezone("America/Sao_Paulo"))
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
        token, _ = createAccessToken({})
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert "exp" in decoded

    def test_create_access_token_with_none_data(self):
        token, _ = createAccessToken(None)
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert "exp" in decoded
