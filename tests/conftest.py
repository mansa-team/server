import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
import factory
from faker import Faker

fake = Faker()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.models.base import Base


@pytest.fixture(autouse=True, scope="function")
def reset_rate_limiter():
    """Reset slowapi in-memory rate limiter between every test."""
    from main.utils.logging_config import limiter

    limiter.reset()


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
def patch_secret_key(monkeypatch):
    from config import Config

    if not Config.USER.JWT_SECRET_KEY:
        monkeypatch.setattr(Config.USER, "JWT_SECRET_KEY", "test-secret-key-not-empty")


TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def dbSession():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def stocksDbSession():
    """Parallel coverability seam for stocks_db (A8).

    Mirrors dbSession but backs config.StocksSessionLocal so tests can
    override the getStocksSession dependency the same way getSession is
    overridden for user_db. No existing test is rewritten; new tests use::

        app.dependency_overrides[getStocksSession] = lambda: stocksDbSession
    """
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingStocksSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingStocksSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def overrideStocksSession(app, session):
    """Wire a stocks_db session into a FastAPI app's dependency overrides.

    Import path matches the app dependency name exactly (config.getStocksSession).
    """
    from config import getStocksSession

    app.dependency_overrides[getStocksSession] = lambda: session
    return app


class UserFactory(factory.DictFactory):
    username = factory.LazyFunction(lambda: fake.user_name())
    email = factory.LazyFunction(lambda: fake.email())
    passwordHash = factory.LazyFunction(lambda: fake.sha256())
    googleId = None
    roles = "USER"


class APIKeyFactory(factory.DictFactory):
    apiKey = factory.LazyFunction(lambda: fake.sha256())
    userId = 1
    requestLimit = 100
    currentUsage = 0


class PrometheusSessionFactory(factory.DictFactory):
    sessionId = factory.LazyFunction(lambda: fake.uuid4())
    userId = 1
    title = factory.LazyFunction(lambda: fake.sentence(nb_words=3))
    summary = factory.LazyFunction(lambda: fake.text(max_nb_chars=80))
    history = factory.LazyFunction(list)


@pytest.fixture
def userFactory():
    return UserFactory


@pytest.fixture
def apiKeyFactory():
    return APIKeyFactory


@pytest.fixture
def prometheusSessionFactory():
    return PrometheusSessionFactory


@pytest.fixture
def sampleUserData(userFactory):
    return userFactory()


@pytest.fixture
def sampleAPIKeyData(apiKeyFactory):
    return apiKeyFactory()


@pytest.fixture
def samplePrometheusSessionData(prometheusSessionFactory):
    return prometheusSessionFactory()


@pytest.fixture
def stocks_http_client():
    """TestClient with stocks router + verifyAPIKey override."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as TestClient
    from main.controller.stocksapi_controller import router as stocksRouter
    from main.utils.errors import registerErrorHandlers
    from main.app.stocks_api.key import verifyAPIKey

    app = FastAPI()
    app.include_router(stocksRouter)
    registerErrorHandlers(app)
    app.dependency_overrides[verifyAPIKey] = lambda: "test-key"

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """TestClient with all routers mounted — no lifespan (no DB/service init).

    Overrides extractTokenPayload dependency so auth-gated endpoints
    don't block input validation tests.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as TestClient
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

    def mock_get_current_user():
        return {"userId": 1, "username": "testuser", "email": "test@example.com", "roles": ["PREMIUM"]}

    testApp.dependency_overrides[UserManager.getCurrentUser] = mock_get_current_user

    with TestClient(testApp, raise_server_exceptions=False) as c:
        yield c


def mock_forgevm(mock_cls):
    """Wire up mock forgevm AsyncClient that returns sandbox with all methods.
    extend_ttl + glob_files so persistence tests work unchanged.
    Call as ``mock_client, mock_sandbox = mock_forgevm(mock_get_client)``.
    """
    mock_client = AsyncMock()
    mock_sandbox = AsyncMock()
    mock_sandbox.id = "sb-mock-123"
    mock_sandbox.exec = AsyncMock(return_value=MagicMock(stdout="Hello\n", stderr=""))
    mock_sandbox.read_file = AsyncMock(return_value="file contents")
    mock_sandbox.write_file = AsyncMock()
    mock_sandbox.list_files = AsyncMock(return_value=[{"path": "/workspace/data.csv", "size": 100, "is_dir": False}])
    mock_sandbox.destroy = AsyncMock()
    mock_sandbox.extend_ttl = AsyncMock()
    mock_sandbox.glob_files = AsyncMock(return_value=[])
    mock_client.spawn = AsyncMock(return_value=mock_sandbox)
    mock_client.get = AsyncMock(return_value=mock_sandbox)
    mock_client.close = AsyncMock()
    mock_cls.return_value = mock_client
    return mock_client, mock_sandbox


# ---------------------------------------------------------------------------
# Shared controller TestClient builders (moved from test_controllers_coverage.py
# so all controller test files reuse one copy). Each returns (client, app,
# mock_session); call sites unpack only what they need.
# ---------------------------------------------------------------------------
def make_auth_client():
    """Return (client, app) with auth + user routers and mocked getSession."""
    from main.controller.authentication_controller import router as authRouter
    from main.controller.user_controller import router as userRouter
    from main.utils.errors import registerErrorHandlers

    app = FastAPI()
    app.include_router(authRouter)
    app.include_router(userRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session
    return TestClient(app, raise_server_exceptions=False), app, mock_session


def make_user_client(mock_current_user=None):
    """Return (client, app) with user router and mocked deps."""
    from main.controller.user_controller import router as userRouter
    from main.utils.errors import registerErrorHandlers
    from main.app.user.user import UserManager

    app = FastAPI()
    app.include_router(userRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session

    if mock_current_user is not None:
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: mock_current_user

    return TestClient(app, raise_server_exceptions=False), app, mock_session


def make_prometheus_client(mock_current_user=None, mock_permission_user=None):
    """Return (client, app) with prometheus router and mocked deps."""
    from main.controller.prometheus_controller import router as promRouter
    from main.utils.errors import registerErrorHandlers
    from main.app.user.user import UserManager

    app = FastAPI()
    app.include_router(promRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session

    user = mock_current_user or {"userId": 1, "username": "testuser", "roles": ["PREMIUM"]}
    # ponytail: per-call Roles.requirePermission returns a fresh callable;
    # override key never matches the actual dep, so the line is a no-op. Skip.
    app.dependency_overrides[UserManager.getCurrentUser] = lambda: user

    return TestClient(app, raise_server_exceptions=False), app, mock_session


def make_stocksapi_client(mock_api_key=None):
    """Return (client, app) with stocks router and mocked deps."""
    from main.controller.stocksapi_controller import router as stocksRouter
    from main.utils.errors import registerErrorHandlers

    app = FastAPI()
    app.include_router(stocksRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session

    if mock_api_key is not None:
        from main.app.stocks_api.key import verifyAPIKey

        app.dependency_overrides[verifyAPIKey] = lambda: mock_api_key

    return TestClient(app, raise_server_exceptions=False), app, mock_session
