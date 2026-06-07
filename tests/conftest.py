import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main.models.base import Base

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def dbSession():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()
    Base.metadata.drop_all(engine)


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
    from main.utils.errors import register_error_handlers

    testApp = FastAPI()
    testApp.include_router(authRouter)
    testApp.include_router(userRouter)
    testApp.include_router(prometheusRouter)
    testApp.include_router(stocksRouter)
    register_error_handlers(testApp)

    # Mock auth dependency so validation tests aren't blocked by 401
    from main.app.user.user import UserManager

    def _mock_get_current_user():
        return {"userId": 1, "username": "testuser", "email": "test@example.com", "roles": ["PREMIUM"]}

    testApp.dependency_overrides[UserManager.getCurrentUser] = _mock_get_current_user

    with _TestClient(testApp, raise_server_exceptions=False) as c:
        yield c
