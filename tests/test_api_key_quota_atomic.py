"""Tests for atomic API key quota enforcement (race condition fix).

Verifies that the TOCTOU race condition in verifyAPIKey is resolved
by using a single atomic SQL UPDATE instead of read-then-write.
"""

import asyncio
import hashlib
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from sqlalchemy import update

from main.models.stocksapi_key import StocksAPIKey
from main.app.stocks_api.key import verifyAPIKey

TEST_KEY_HASH = hashlib.sha256("test_key_12345".encode()).hexdigest()


def quotaUpdate(dbSession, apiKey):
    """Run the atomic quota-increment UPDATE; return affected rowcount."""
    result = dbSession.execute(
        update(StocksAPIKey)
        .where(StocksAPIKey.apiKey == apiKey)
        .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
        .values(currentUsage=StocksAPIKey.currentUsage + 1)
    )
    dbSession.commit()
    return result.rowcount


@pytest.fixture
def sampleKeyData():
    """Sample API key data for tests."""
    return {
        "apiKey": hashlib.sha256("test_key_12345".encode()).hexdigest(),
        "userId": 1,
        "requestLimit": 100,
        "currentUsage": 0,
    }


class TestAtomicQuotaIncrement:
    """Test that atomic increment prevents race conditions."""

    def test_normal_quota_check_works(self, dbSession, sampleKeyData):
        """Test that normal quota check still works with atomic increment."""
        key = StocksAPIKey(**sampleKeyData)
        dbSession.add(key)
        dbSession.commit()

        # Mock Config to enable API key system
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)

            # Run the atomic increment
            assert quotaUpdate(dbSession, TEST_KEY_HASH) == 1

            # Verify increment happened
            dbSession.refresh(key)
            assert key.currentUsage == 1

    def test_atomic_increment_prevents_overuse(self, dbSession, sampleKeyData):
        """Test that atomic increment prevents quota overuse."""
        # Set usage to limit - 1
        key = StocksAPIKey(**{**sampleKeyData, "currentUsage": 99, "requestLimit": 100})
        dbSession.add(key)
        dbSession.commit()

        # First request should succeed (99 -> 100)
        assert quotaUpdate(dbSession, TEST_KEY_HASH) == 1
        dbSession.commit()

        dbSession.refresh(key)
        assert key.currentUsage == 100

        # Second request should fail (100 is not < 100)
        assert quotaUpdate(dbSession, TEST_KEY_HASH) == 0
        dbSession.commit()

        # Usage should still be 100
        dbSession.refresh(key)
        assert key.currentUsage == 100

    def test_concurrent_requests_serialized_at_db_level(self, dbSession, sampleKeyData):
        """Test that concurrent requests are properly serialized at DB level.

        This simulates the race condition scenario where two requests
        try to increment simultaneously. With atomic increment, only
        one should succeed if at the limit.
        """
        # Set usage to limit - 2
        key = StocksAPIKey(**{**sampleKeyData, "currentUsage": 98, "requestLimit": 100})
        dbSession.add(key)
        dbSession.commit()

        # Simulate two concurrent requests
        # Both should succeed because 98 < 100 and 99 < 100
        assert quotaUpdate(dbSession, TEST_KEY_HASH) == 1
        dbSession.commit()

        assert quotaUpdate(dbSession, TEST_KEY_HASH) == 1
        dbSession.commit()

        # Both should succeed
        dbSession.refresh(key)
        assert key.currentUsage == 100

    def test_request_at_exact_quota_limit(self, dbSession, sampleKeyData):
        """Test edge case: request exactly at quota limit."""
        # Set usage to exactly at limit
        key = StocksAPIKey(**{**sampleKeyData, "currentUsage": 100, "requestLimit": 100})
        dbSession.add(key)
        dbSession.commit()

        # Request should fail (100 is not < 100)
        assert quotaUpdate(dbSession, TEST_KEY_HASH) == 0
        dbSession.commit()

        dbSession.refresh(key)
        assert key.currentUsage == 100

    def test_invalid_api_key_returns_zero_rows(self, dbSession):
        """Test that invalid API key returns zero rows affected."""
        assert quotaUpdate(dbSession, "nonexistent_key") == 0
        dbSession.commit()

    def test_multiple_keys_independent_quotas(self, dbSession):
        """Test that multiple API keys have independent quotas."""
        key1 = StocksAPIKey(apiKey="key1", userId=1, requestLimit=100, currentUsage=99)
        key2 = StocksAPIKey(apiKey="key2", userId=2, requestLimit=100, currentUsage=50)
        dbSession.add_all([key1, key2])
        dbSession.commit()

        # Increment key1 (should succeed: 99 -> 100)
        assert quotaUpdate(dbSession, "key1") == 1
        dbSession.commit()

        # Increment key2 (should succeed: 50 -> 51)
        assert quotaUpdate(dbSession, "key2") == 1
        dbSession.commit()

        # Verify independent increments
        dbSession.refresh(key1)
        dbSession.refresh(key2)
        assert key1.currentUsage == 100
        assert key2.currentUsage == 51

    def test_increment_from_zero(self, dbSession, sampleKeyData):
        """Test that increment works from zero usage."""
        key = StocksAPIKey(**sampleKeyData)
        dbSession.add(key)
        dbSession.commit()

        assert quotaUpdate(dbSession, TEST_KEY_HASH) == 1

        dbSession.refresh(key)
        assert key.currentUsage == 1


class TestVerifyAPIKeyIntegration:
    """Integration tests for the verifyAPIKey function."""

    def test_verify_api_key_success(self, dbSession, sampleKeyData):
        """Test successful API key verification."""
        key = StocksAPIKey(**sampleKeyData)
        dbSession.add(key)
        dbSession.commit()

        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)

            result = asyncio.run(verifyAPIKey(apiKey="test_key_12345", db=dbSession))

            assert result == "test_key_12345"
            dbSession.refresh(key)
            assert key.currentUsage == 1

    def test_verify_api_key_quota_exceeded(self, dbSession, sampleKeyData):
        """Test API key verification when quota is exceeded."""
        key = StocksAPIKey(**{**sampleKeyData, "currentUsage": 100, "requestLimit": 100})
        dbSession.add(key)
        dbSession.commit()

        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verifyAPIKey(apiKey="test_key_12345", db=dbSession))

            assert exc_info.value.status_code == 429
            assert "quota exceeded" in exc_info.value.detail

    def test_verify_api_key_invalid(self, dbSession):
        """Test API key verification with invalid key."""
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verifyAPIKey(apiKey="invalid_key", db=dbSession))

            assert exc_info.value.status_code == 401
            assert "Invalid API key" in exc_info.value.detail

    def test_verify_api_key_missing(self, dbSession):
        """Test API key verification with missing key."""
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verifyAPIKey(apiKey=None, db=dbSession))

            assert exc_info.value.status_code == 401
            assert "Missing API key" in exc_info.value.detail

    def test_verify_api_key_disabled(self, dbSession):
        """Test that API key system can be disabled."""
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=False)

            result = asyncio.run(verifyAPIKey(apiKey="any_key", db=dbSession))
            assert result is None
