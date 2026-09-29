import pytest
from main.models.user import User
from main.models.stocksapi_key import StocksAPIKey
from main.models.orunmila import OrunmilaSession
from main.app.user.user import UserManager
from datetime import datetime, timedelta


class TestUserModel:
    def test_create_user(self, dbSession, sampleUserData):
        user = User(**sampleUserData)
        dbSession.add(user)
        dbSession.commit()

        assert user.userId is not None
        assert user.username == sampleUserData["username"]
        assert user.email == sampleUserData["email"]
        assert user.roles == sampleUserData["roles"]

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


class TestStocksAPIKeyModel:
    def test_create_api_key(self, dbSession, sampleAPIKeyData):
        key = StocksAPIKey(**sampleAPIKeyData)
        dbSession.add(key)
        dbSession.commit()

        assert key.apiKey == sampleAPIKeyData["apiKey"]
        assert key.userId == sampleAPIKeyData["userId"]
        assert key.requestLimit == sampleAPIKeyData["requestLimit"]


class TestOrunmilaSessionModel:
    def test_create_session(self, dbSession, sampleOrunmilaSessionData):
        session = OrunmilaSession(**sampleOrunmilaSessionData)
        dbSession.add(session)
        dbSession.commit()

        assert session.sessionId == sampleOrunmilaSessionData["sessionId"]
        assert session.userId == sampleOrunmilaSessionData["userId"]
        assert session.title == sampleOrunmilaSessionData["title"]

    def test_default_history(self, dbSession, sampleOrunmilaSessionData):
        session = OrunmilaSession(**sampleOrunmilaSessionData)
        dbSession.add(session)
        dbSession.commit()

        assert session.history == []
