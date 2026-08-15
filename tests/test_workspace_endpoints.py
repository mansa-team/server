"""Tests for /prometheus/workspace/* endpoints (delete, download, list).

NOTE: the direct /workspace/upload route was REMOVED by design — the agent
owns the workspace via the write_file tool (user directive 2026-08-15).
"""

import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient as _TestClient

from main.utils.errors import registerErrorHandlers
from main.app.user.user import UserManager


def _make_client():
    """Minimal app with the prometheus router; auth deps stubbed."""
    from main.controller.prometheus_controller import router as promRouter

    app = FastAPI()
    app.include_router(promRouter)
    registerErrorHandlers(app)

    mock_db = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_db
    app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
        "userId": 1,
        "username": "alice",
        "roles": ["PREMIUM"],
    }

    with patch("main.controller.prometheus_controller.Roles") as mock_roles:

        async def mock_checker(user=None, **kwargs):
            return user or {"userId": 1, "username": "alice", "roles": ["PREMIUM"]}

        mock_roles.requirePermission.return_value = mock_checker

        return _TestClient(app, raise_server_exceptions=False)


class TestWorkspaceDelete:
    def test_delete_file(self):
        with patch("main.controller.prometheus_controller.SandboxManager.delete_file", return_value=True) as m:
            client = _make_client()
            resp = client.request(
                "DELETE",
                "/prometheus/workspace/delete",
                json={"path": "/workspace/old.csv"},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        m.assert_called_once_with(1, "/workspace/old.csv")

    def test_delete_missing_file_returns_404(self):
        with patch("main.controller.prometheus_controller.SandboxManager.delete_file", return_value=False):
            client = _make_client()
            resp = client.request(
                "DELETE",
                "/prometheus/workspace/delete",
                json={"path": "/workspace/ghost.csv"},
            )
        assert resp.status_code == 404


class TestWorkspaceDownload:
    def test_download_returns_file(self):
        from fastapi.responses import FileResponse
        from main.controller import prometheus_controller as ctrl

        with (
            patch.object(ctrl, "hostPath") as m_host,
            patch.object(ctrl, "FileResponse", wraps=FileResponse) as m_fr,
        ):
            fake_path = MagicMock()
            fake_path.exists.return_value = True
            fake_path.is_file.return_value = True
            fake_path.name = "data.csv"
            m_host.return_value = fake_path

            client = _make_client()
            resp = client.get("/prometheus/workspace/download", params={"path": "/workspace/data.csv"})

        assert resp.status_code == 200
        m_fr.assert_called_once_with(fake_path, filename="data.csv")

    def test_download_missing_file_404(self):
        with patch("main.controller.prometheus_controller.hostPath") as m_host:
            fake_path = MagicMock()
            fake_path.exists.return_value = False
            m_host.return_value = fake_path

            client = _make_client()
            resp = client.get("/prometheus/workspace/download", params={"path": "/workspace/ghost.csv"})
        assert resp.status_code == 404

    def test_download_rejects_traversal(self):
        with patch("main.controller.prometheus_controller.hostPath", side_effect=ValueError("Invalid workspace path")):
            client = _make_client()
            resp = client.get("/prometheus/workspace/download", params={"path": "/workspace/../../etc/passwd"})
        assert resp.status_code == 400


class TestWorkspaceList:
    def test_list_returns_entries(self):
        with patch(
            "main.controller.prometheus_controller.SandboxManager.list_files", return_value={"entries": []}
        ) as m:
            client = _make_client()
            resp = client.get("/prometheus/workspace/list")
        assert resp.status_code == 200
        assert resp.json() == {"entries": []}
        m.assert_called_once_with(1, "/workspace")

    def test_list_rejects_traversal(self):
        client = _make_client()
        resp = client.get("/prometheus/workspace/list", params={"path": "/workspace/../../etc"})
        assert resp.status_code == 400
