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
