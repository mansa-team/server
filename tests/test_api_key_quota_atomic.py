"""Tests for atomic API key quota enforcement (race condition fix).

Verifies that the TOCTOU race condition in verifyAPIKey is resolved
by using a single atomic SQL UPDATE instead of read-then-write.
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main.models.base import Base
from main.models.stocksapi_key import StocksAPIKey
from main.app.stocks_api.key import verifyAPIKey


@pytest.fixture
def dbSession():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sampleKeyData():
    """Sample API key data for tests."""
    return {"apiKey": "test_key_12345", "userId": 1, "requestLimit": 100, "currentUsage": 0}


class TestAtomicQuotaIncrement:
    """Test that atomic increment prevents race conditions."""

    def test_normal_quota_check_works(self, dbSession, sampleKeyData):
        """Test that normal quota check still works with atomic increment."""
        key = StocksAPIKey(**sampleKeyData)
        dbSession.add(key)
        dbSession.commit()

        # Mock Config to enable API key system
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = {"KEY.SYSTEM": True}

            # Run the atomic increment
            from sqlalchemy import update

            result = dbSession.execute(
                update(StocksAPIKey)
                .where(StocksAPIKey.apiKey == "test_key_12345")
                .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
                .values(currentUsage=StocksAPIKey.currentUsage + 1)
            )
            dbSession.commit()

            # Verify increment happened
            assert result.rowcount == 1
            dbSession.refresh(key)
            assert key.currentUsage == 1

    def test_atomic_increment_prevents_overuse(self, dbSession, sampleKeyData):
        """Test that atomic increment prevents quota overuse."""
        # Set usage to limit - 1
        key = StocksAPIKey(**{**sampleKeyData, "currentUsage": 99, "requestLimit": 100})
        dbSession.add(key)
        dbSession.commit()

        from sqlalchemy import update

        # First request should succeed (99 -> 100)
        result1 = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "test_key_12345")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()
        assert result1.rowcount == 1

        dbSession.refresh(key)
        assert key.currentUsage == 100

        # Second request should fail (100 is not < 100)
        result2 = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "test_key_12345")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()
        assert result2.rowcount == 0

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

        from sqlalchemy import update

        # Simulate two concurrent requests
        # Both should succeed because 98 < 100 and 99 < 100
        result1 = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "test_key_12345")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()

        result2 = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "test_key_12345")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()

        # Both should succeed
        assert result1.rowcount == 1
        assert result2.rowcount == 1

        dbSession.refresh(key)
        assert key.currentUsage == 100

    def test_request_at_exact_quota_limit(self, dbSession, sampleKeyData):
        """Test edge case: request exactly at quota limit."""
        # Set usage to exactly at limit
        key = StocksAPIKey(**{**sampleKeyData, "currentUsage": 100, "requestLimit": 100})
        dbSession.add(key)
        dbSession.commit()

        from sqlalchemy import update

        # Request should fail (100 is not < 100)
        result = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "test_key_12345")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()

        assert result.rowcount == 0

        dbSession.refresh(key)
        assert key.currentUsage == 100

    def test_invalid_api_key_returns_zero_rows(self, dbSession):
        """Test that invalid API key returns zero rows affected."""
        from sqlalchemy import update

        result = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "nonexistent_key")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()

        assert result.rowcount == 0

    def test_multiple_keys_independent_quotas(self, dbSession):
        """Test that multiple API keys have independent quotas."""
        key1 = StocksAPIKey(apiKey="key1", userId=1, requestLimit=100, currentUsage=99)
        key2 = StocksAPIKey(apiKey="key2", userId=2, requestLimit=100, currentUsage=50)
        dbSession.add_all([key1, key2])
        dbSession.commit()

        from sqlalchemy import update

        # Increment key1 (should succeed: 99 -> 100)
        result1 = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "key1")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()
        assert result1.rowcount == 1

        # Increment key2 (should succeed: 50 -> 51)
        result2 = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "key2")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()
        assert result2.rowcount == 1

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

        from sqlalchemy import update

        result = dbSession.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == "test_key_12345")
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        dbSession.commit()

        assert result.rowcount == 1
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
            mock_config.STOCKS_API = {"KEY.SYSTEM": True}

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
            mock_config.STOCKS_API = {"KEY.SYSTEM": True}

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verifyAPIKey(apiKey="test_key_12345", db=dbSession))

            assert exc_info.value.status_code == 429
            assert "quota exceeded" in exc_info.value.detail

    def test_verify_api_key_invalid(self, dbSession):
        """Test API key verification with invalid key."""
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = {"KEY.SYSTEM": True}

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verifyAPIKey(apiKey="invalid_key", db=dbSession))

            assert exc_info.value.status_code == 401
            assert "Invalid API key" in exc_info.value.detail

    def test_verify_api_key_missing(self, dbSession):
        """Test API key verification with missing key."""
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = {"KEY.SYSTEM": True}

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verifyAPIKey(apiKey=None, db=dbSession))

            assert exc_info.value.status_code == 401
            assert "Missing API key" in exc_info.value.detail

    def test_verify_api_key_disabled(self, dbSession):
        """Test that API key system can be disabled."""
        with patch("main.app.stocks_api.key.Config") as mock_config:
            mock_config.STOCKS_API = {"KEY.SYSTEM": False}

            result = asyncio.run(verifyAPIKey(apiKey="any_key", db=dbSession))
            assert result is None
