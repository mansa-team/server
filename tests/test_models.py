import pytest
from main.models.user import User
from main.models.stocksapi_key import StocksAPIKey
from main.models.prometheus import PrometheusSession
from main.app.user.user import UserManager
from main.app.stocks_api.key import (
    isQuotaExceeded,
    needsReset,
    resetQuota,
    incrementUsage,
    getRemainingQuota,
    keyToDict,
)
from datetime import datetime, timedelta


class TestUserModel:
    def test_create_user(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        dbSession.add(user)
        dbSession.commit()

        assert user.userId is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.roles == "USER"

    def test_get_roles_list_default(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = None
        assert UserManager.getRolesList(user) == ["USER"]

    def test_get_roles_list_single_role(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = "ADMIN"
        assert UserManager.getRolesList(user) == ["ADMIN"]

    def test_get_roles_list_multiple_roles(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = "ADMIN,USER,PREMIUM"
        roles = UserManager.getRolesList(user)
        assert "ADMIN" in roles
        assert "USER" in roles
        assert "PREMIUM" in roles

    def test_add_role_new(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = "USER"
        UserManager.addRole(user, "ADMIN")
        assert "ADMIN" in UserManager.getRolesList(user)

    def test_add_role_existing(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = "USER,ADMIN"
        initialRoles = UserManager.getRolesList(user)
        UserManager.addRole(user, "ADMIN")
        assert UserManager.getRolesList(user) == initialRoles

    def test_has_role_true(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = "USER,ADMIN"
        assert UserManager.hasRole(user, "ADMIN") is True

    def test_has_role_false(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = "USER"
        assert UserManager.hasRole(user, "ADMIN") is False

    def test_has_role_with_enum(self, dbSession, sampleUserData):
        class MockEnum:
            name = "ADMIN"

        user = User(**sampleUserData)
        user.roles = "ADMIN"
        assert UserManager.hasRole(user, MockEnum()) is True

    def test_toDict(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        user.roles = "USER,ADMIN"
        result = UserManager.toDict(user)

        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert "ADMIN" in result["roles"]
        assert "USER" in result["roles"]


class TestStocksAPIKeyModel:
    def test_create_api_key(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        dbSession.add(key)
        dbSession.commit()

        assert key.apiKey == "test_api_key_12345"
        assert key.userId == 1
        assert key.requestLimit == 100

    def test_is_quota_exceeded_true(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.currentUsage = 100
        key.requestLimit = 100
        assert isQuotaExceeded(key) is True

    def test_is_quota_exceeded_false(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.currentUsage = 50
        key.requestLimit = 100
        assert isQuotaExceeded(key) is False

    def test_needs_reset_true_no_last_reset(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.lastReset = None
        assert needsReset(key, 30) is True

    def test_needs_reset_true_expired(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.lastReset = datetime.now() - timedelta(days=31)
        assert needsReset(key, 30) is True

    def test_needs_reset_false_recent(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.lastReset = datetime.now() - timedelta(days=5)
        assert needsReset(key, 30) is False

    def test_reset_quota(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.currentUsage = 50
        resetQuota(key)

        assert key.currentUsage == 0
        assert key.lastReset is not None

    def test_increment_usage(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.currentUsage = 10
        incrementUsage(key)
        assert key.currentUsage == 11

    def test_get_remaining_quota(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.currentUsage = 30
        key.requestLimit = 100
        assert getRemainingQuota(key) == 70

    def test_get_remaining_quota_exceeded(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        key.currentUsage = 150
        key.requestLimit = 100
        assert getRemainingQuota(key) == 0

    def test_toDict(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        result = keyToDict(key)

        assert result["apiKey"] == "test_api_key_12345"
        assert result["userId"] == 1
        assert result["requestLimit"] == 100
        assert result["currentUsage"] == 0
        assert result["remainingQuota"] == 100


class TestPrometheusSessionModel:
    def test_create_session(self, dbSession, samplePrometheusSessionData):
        session = PrometheusSession(**samplePrometheusSessionData)
        dbSession.add(session)
        dbSession.commit()

        assert session.sessionId == "session_123"
        assert session.userId == 1
        assert session.title == "Test Session"

    def test_default_history(self, dbSession, samplePrometheusSessionData):
        session = PrometheusSession(**samplePrometheusSessionData)
        dbSession.add(session)
        dbSession.commit()

        assert session.history == []
