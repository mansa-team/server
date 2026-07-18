"""Tests for input validation via HTTP endpoints.

Validation is now inline via Body(...) parameters in controllers.
These tests verify validation through the TestClient.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestRegisterValidation:
    """POST /auth/register — validates username, email, password via Body(...)"""

    def test_valid_registration(self, client):
        response = client.post(
            "/auth/register",
            json={"username": "Alice", "email": "alice@example.com", "password": "secret123"},
        )
        # Should not be 422 (validation error) — may be 200, 409, or 500 depending on DB
        assert response.status_code != 422

    def test_username_too_short(self, client):
        response = client.post(
            "/auth/register",
            json={"username": "", "email": "alice@example.com", "password": "secret123"},
        )
        assert response.status_code == 422

    def test_username_too_long(self, client):
        response = client.post(
            "/auth/register",
            json={"username": "A" * 101, "email": "alice@example.com", "password": "secret123"},
        )
        assert response.status_code == 422

    def test_email_too_short(self, client):
        response = client.post(
            "/auth/register",
            json={"username": "Alice", "email": "a@b", "password": "secret123"},
        )
        assert response.status_code == 422

    def test_password_too_short(self, client):
        response = client.post(
            "/auth/register",
            json={"username": "Alice", "email": "alice@example.com", "password": "ab"},
        )
        assert response.status_code == 422


class TestLoginValidation:
    """POST /auth/login — validates username, password via Body(...)"""

    def test_valid_login_payload(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "Alice", "password": "secret123"},
        )
        # Should not be 422 — may be 200 or 401 depending on DB
        assert response.status_code != 422

    def test_username_too_short(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "", "password": "secret123"},
        )
        assert response.status_code == 422

    def test_password_too_short(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "Alice", "password": "ab"},
        )
        assert response.status_code == 422


class TestPrometheusSessionValidation:
    """POST /prometheus/sessions — validates title via Body(...)"""

    def test_valid_create_session(self, client):
        response = client.post(
            "/prometheus/sessions",
            json={"title": "New Chat"},
            headers={"X-Access-Token": "valid-token"},
        )
        # Should not be 422 — may be 200/201 or 401 depending on auth
        assert response.status_code != 422

    def test_empty_title(self, client):
        response = client.post(
            "/prometheus/sessions",
            json={"title": ""},
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 422

    def test_title_too_long(self, client):
        response = client.post(
            "/prometheus/sessions",
            json={"title": "T" * 201},
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 422


class TestUpdateTitleValidation:
    """PUT /prometheus/sessions/{sessionId} — validates title via Body(...)"""

    def test_empty_title(self, client):
        response = client.put(
            "/prometheus/sessions/1",
            json={"title": ""},
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 422

    def test_title_too_long(self, client):
        response = client.put(
            "/prometheus/sessions/1",
            json={"title": "T" * 201},
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 422


class TestChatValidation:
    """POST /prometheus/chat/stream — validates query via Body(...)"""

    def test_empty_text(self, client):
        response = client.post(
            "/prometheus/chat/stream",
            json={"query": ""},
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 422

    def test_text_too_long(self, client):
        response = client.post(
            "/prometheus/chat/stream",
            json={"query": "X" * 10001},
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 422

    def test_max_length_boundary(self, client):
        response = client.post(
            "/prometheus/chat/stream",
            json={"query": "X" * 10000},
            headers={"X-Access-Token": "valid-token"},
        )
        # Should not be 422 — may be other error
        assert response.status_code != 422


class TestMissingBody:
    """Test that endpoints reject requests with missing required fields."""

    def test_register_missing_username(self, client):
        response = client.post(
            "/auth/register",
            json={"email": "alice@example.com", "password": "secret123"},
        )
        assert response.status_code == 422

    def test_register_missing_all(self, client):
        response = client.post("/auth/register", json={})
        assert response.status_code == 422

    def test_login_missing_fields(self, client):
        response = client.post("/auth/login", json={})
        assert response.status_code == 422
