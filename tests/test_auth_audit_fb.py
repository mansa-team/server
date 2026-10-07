"""F-B audit tests: fail-closed sessionId, atomic revoke, 30d expiry + idle, unique SSO usernames."""

import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.authentication import constants as authConstants
from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.session import SessionManager
from main.app.user.user import UserManager
from main.models.user import User


def makeUser(dbSession, username="fb_user"):
    user = User(username=username, email=f"{username}@example.com", passwordHash="hashed", roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    return user


class TestFailClosed:
    def test_missing_session_id_rejected(self):
        db = MagicMock()
        with patch.object(SessionManager, "validateSession") as mv:
            with pytest.raises(HTTPException) as e:
                UserManager.getCurrentUser(MagicMock(headers={}), payload={"userId": 1}, db=db)
        assert e.value.status_code == 401
        assert e.value.detail == "Session required"
        mv.assert_not_called()

    def test_missing_user_id_rejected(self):
        db = MagicMock()
        with pytest.raises(HTTPException) as e:
            UserManager.getCurrentUser(MagicMock(headers={}), payload={"sessionId": "abc"}, db=db)
        assert e.value.status_code == 401


class TestRevokeAllExcept:
    def test_signature_and_behavior(self):
        assert list(inspect.signature(SessionManager.revokeAllExcept).parameters) == [
            "db",
            "user_id",
            "keep_session_id",
        ]
        db = MagicMock()
        assert SessionManager.revokeAllExcept(db, 7, "keep-1") is None
        db.commit.assert_called_once()
        query = db.query.return_value
        query.filter.assert_called_once()
        query.filter.return_value.update.assert_called_once()
        filterArgs = query.filter.call_args[0]
        sessionArg = next(a for a in filterArgs if getattr(getattr(a, "left", None), "key", "") == "sessionId")
        assert sessionArg.right.value == "keep-1"


class TestAtomicRevoke:
    def _mockDb(self, count):
        db = MagicMock()
        db.query.return_value.filter.return_value.update.return_value = count
        return db

    def test_revoke_found(self):
        db = self._mockDb(1)
        assert SessionManager.revokeSession(db, "s", 1) is True
        db.commit.assert_called_once()

    def test_revoke_not_found(self):
        db = self._mockDb(0)
        assert SessionManager.revokeSession(db, "s", 1) is False

    def test_no_select_before_update(self):
        db = self._mockDb(1)
        SessionManager.revokeSession(db, "s", 1)
        db.query.return_value.filter.return_value.first.assert_not_called()


class TestExpiryIdle:
    def test_constants(self):
        assert authConstants.SESSION_EXPIRY_DAYS == 30
        assert authConstants.TOKEN_EXPIRY_HOURS == 30 * 24
        assert authConstants.SESSION_IDLE_TIMEOUT_HOURS == 24

    def test_fresh_session_valid_and_touched(self, dbSession):
        user = makeUser(dbSession)
        session = SessionManager.createSession(dbSession, user.userId, "pytest")
        before = session.lastActivityAt
        assert SessionManager.validateSession(dbSession, session.sessionId, user.userId) is True
        dbSession.refresh(session)
        assert session.lastActivityAt >= before

    def test_idle_session_revoked(self, dbSession):
        user = makeUser(dbSession, username="fb_idle")
        session = SessionManager.createSession(dbSession, user.userId, "pytest")
        session.lastActivityAt = datetime.now(timezone.utc) - timedelta(days=2)
        dbSession.commit()
        assert SessionManager.validateSession(dbSession, session.sessionId, user.userId) is False
        dbSession.refresh(session)
        assert session.isActive is False


class TestUniqueUsername:
    def _mockDb(self, side_effect):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = side_effect
        return db

    def test_free_base_returned(self):
        assert AuthenticationManager.resolveUniqueUsername(self._mockDb([None]), "base") == "base"

    def test_taken_base_gets_suffix(self):
        assert AuthenticationManager.resolveUniqueUsername(self._mockDb([MagicMock(), None]), "base") == "base-1"

    def test_always_taken_raises_409(self):
        with pytest.raises(HTTPException) as e:
            AuthenticationManager.resolveUniqueUsername(self._mockDb(MagicMock()), "base")
        assert e.value.status_code == 409
