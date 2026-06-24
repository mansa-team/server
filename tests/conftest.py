import pytest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.models.base import Base


def pytest_configure(config):
    """Set required env vars before test collection.

    config.py eagerly instantiates UserSettings() at import time, which
    requires JWT_SECRET_KEY and SESSION_SECRET_KEY. These env vars
    don't exist in CI, so every test that touches config blows up
    during collection. This hook runs before collection begins.
    """
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
    os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key-not-for-production")


@pytest.fixture(autouse=True)
def _patch_secret_key(monkeypatch):
    import main.app.authentication.constants as auth_constants

    if not auth_constants.SECRET_KEY:
        monkeypatch.setattr(auth_constants, "SECRET_KEY", "test-secret-key-not-empty")
        # util.py imports SECRET_KEY via `from ... import`, creating a separate binding
        import main.app.authentication.util as auth_util

        monkeypatch.setattr(auth_util, "SECRET_KEY", "test-secret-key-not-empty")


TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def dbSession():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sampleUserData():
    return {
        "username": "testuser",
        "email": "test@example.com",
        "passwordHash": "hashed_password",
        "googleId": None,
        "roles": "USER",
    }


@pytest.fixture
def sampleAPIKeyData():
    return {"apiKey": "test_api_key_12345", "userId": 1, "requestLimit": 100, "currentUsage": 0}


@pytest.fixture
def samplePrometheusSessionData():
    return {"sessionId": "session_123", "userId": 1, "title": "Test Session", "summary": "Test summary", "history": []}


@pytest.fixture
def stocks_http_client():
    """TestClient with stocks router + verifyAPIKey + getCurrentUser overrides."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as _TestClient
    from main.controller.stocksapi_controller import router as stocksRouter
    from main.utils.errors import registerErrorHandlers
    from main.app.user.user import UserManager
    from main.app.stocks_api.key import verifyAPIKey

    app = FastAPI()
    app.include_router(stocksRouter)
    registerErrorHandlers(app)
    app.dependency_overrides[verifyAPIKey] = lambda: "test-key"
    app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
        "userId": 1,
        "username": "test",
        "roles": ["USER"],
    }

    with _TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """TestClient with all routers mounted — no lifespan (no DB/service init).

    Overrides extractTokenPayload dependency so auth-gated endpoints
    don't block input validation tests.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as _TestClient
    from main.controller.authentication_controller import router as authRouter
    from main.controller.user_controller import router as userRouter
    from main.controller.prometheus_controller import router as prometheusRouter
    from main.controller.stocksapi_controller import router as stocksRouter
    from main.utils.errors import registerErrorHandlers

    testApp = FastAPI()
    testApp.include_router(authRouter)
    testApp.include_router(userRouter)
    testApp.include_router(prometheusRouter)
    testApp.include_router(stocksRouter)
    registerErrorHandlers(testApp)

    # Mock auth dependency so validation tests aren't blocked by 401
    from main.app.user.user import UserManager

    def _mock_get_current_user():
        return {"userId": 1, "username": "testuser", "email": "test@example.com", "roles": ["PREMIUM"]}

    testApp.dependency_overrides[UserManager.getCurrentUser] = _mock_get_current_user

    with _TestClient(testApp, raise_server_exceptions=False) as c:
        yield c
