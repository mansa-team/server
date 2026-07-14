import pytest
from unittest.mock import patch, MagicMock

# Ensure UserMemory is registered with Base
import main.models.memory  # noqa: F401

MOCK_EMBED = [[0.1] * 384]


class TestMemoryControllerRoutes:
    """Verify memory endpoints exist and are wired correctly."""

    def test_get_memories_endpoint_exists(self, client):
        """GET /prometheus/memories exists."""
        # Will 500 because no real DB, but endpoint exists and auth passes
        resp = client.get("/prometheus/memories")
        assert resp.status_code != 404

    def test_post_memories_endpoint_exists(self, client):
        """POST /prometheus/memories exists."""
        resp = client.post("/prometheus/memories", json={"key": "k", "value": "v"})
        assert resp.status_code != 404

    def test_delete_memories_endpoint_exists(self, client):
        """DELETE /prometheus/memories/{id} exists."""
        resp = client.delete("/prometheus/memories/1")
        assert resp.status_code != 404

    def test_get_memories_rejects_unauthenticated(self):
        """GET /memories requires authentication."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient as _TestClient
        from main.controller.prometheus_controller import router as prometheusRouter
        from main.utils.errors import registerErrorHandlers

        app = FastAPI()
        app.include_router(prometheusRouter)
        registerErrorHandlers(app)
        # No auth override → 401/403

        with _TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/prometheus/memories")
            assert resp.status_code in (401, 403)
        app.dependency_overrides.clear()

    def test_get_memories_rejects_basic_user(self, dbSession):
        """GET /memories requires USE_PROMETHEUS (basic USER role denied)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient as _TestClient
        from main.controller.prometheus_controller import router as prometheusRouter
        from main.utils.errors import registerErrorHandlers
        from main.app.user.user import UserManager
        from config import getSession as _real_get_session

        app = FastAPI()
        app.include_router(prometheusRouter)
        registerErrorHandlers(app)

        def _mock_basic_user():
            return {"userId": 1, "username": "basic", "roles": ["USER"]}

        def _mock_session():
            yield dbSession

        app.dependency_overrides[UserManager.getCurrentUser] = _mock_basic_user
        app.dependency_overrides[_real_get_session] = _mock_session

        with _TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/prometheus/memories")
            assert resp.status_code == 403
        app.dependency_overrides.clear()


class TestMemoryEndpointsIntegration:
    """Full integration tests using mocked MemoryManager."""

    @patch("main.app.prometheus.memory.MemoryManager")
    def test_get_memories_calls_manager(self, mock_mm, client):
        """GET /memories delegates to MemoryManager."""
        mock_mm.get_user_memories.return_value = [
            {"id": 1, "memoryKey": "k", "memoryValue": "v", "memoryType": "context",
             "relevanceScore": 1.0, "accessCount": 0, "createdAt": "2026-01-01"}
        ]
        mock_mm.count_memories.return_value = 1

        resp = client.get("/prometheus/memories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["memories"]) == 1
        mock_mm.get_user_memories.assert_called_once()

    @patch("main.utils.models.loader.embed", return_value=MOCK_EMBED)
    @patch("main.app.prometheus.memory.MemoryManager")
    def test_create_memory_calls_manager(self, mock_mm, mock_embed, client):
        """POST /memories delegates to MemoryManager."""
        mock_memory = MagicMock()
        mock_memory.id = 42
        mock_mm.upsert_memory.return_value = {"status": "created", "memory": mock_memory}

        resp = client.post("/prometheus/memories", json={
            "key": "fav", "value": "PETR4", "memoryType": "preference",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["memoryId"] == 42
        mock_mm.upsert_memory.assert_called_once()

    @patch("main.utils.models.loader.embed", return_value=MOCK_EMBED)
    @patch("main.app.prometheus.memory.MemoryManager")
    def test_create_memory_limit_reached(self, mock_mm, mock_embed, client):
        """POST /memories returns 403 when limit reached."""
        mock_mm.upsert_memory.return_value = {"status": "limit_reached", "limit": 5, "current": 5}

        resp = client.post("/prometheus/memories", json={
            "key": "overflow", "value": "blocked", "memoryType": "context",
        })
        assert resp.status_code == 403
        assert "limit" in resp.text.lower()

    @patch("main.app.prometheus.memory.MemoryManager")
    def test_delete_memory_calls_manager(self, mock_mm, client):
        """DELETE /memories/{id} delegates to MemoryManager."""
        mock_mm.delete_memory.return_value = True

        resp = client.delete("/prometheus/memories/42")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        mock_mm.delete_memory.assert_called_once()

    @patch("main.app.prometheus.memory.MemoryManager")
    def test_delete_memory_not_found(self, mock_mm, client):
        """DELETE /memories/{id} returns 404 when not found."""
        mock_mm.delete_memory.return_value = False

        resp = client.delete("/prometheus/memories/9999")
        assert resp.status_code == 404

    def test_create_memory_missing_key(self, client):
        """POST /memories rejects missing key."""
        resp = client.post("/prometheus/memories", json={"value": "v"})
        assert resp.status_code == 422

    def test_create_memory_missing_value(self, client):
        """POST /memories rejects missing value."""
        resp = client.post("/prometheus/memories", json={"key": "k"})
        assert resp.status_code == 422
