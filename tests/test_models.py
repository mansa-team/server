import pytest
from main.models.user import User
from main.models.stocksapi_key import StocksAPIKey
from main.models.prometheus import PrometheusSession
from main.app.user.user import UserManager
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
