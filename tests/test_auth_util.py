import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.authentication.util import hashPassword, verifyPassword, createAccessToken
from datetime import timedelta
from datetime import timedelta, datetime, timezone
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

        expTime = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        hoursDiff = (expTime - now).total_seconds() / 3600

        assert 47 <= hoursDiff <= 49

    def test_create_access_token_contains_data(self):
        data = {"userId": "456", "username": "testuser"}
        token, _ = createAccessToken(data)
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert decoded["userId"] == "456"
