"""Tests for SandboxManager file mutation helpers (delete_file, write_bytes)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from main.app.prometheus.sandbox import SandboxManager, hostPath


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    # Point WORKSPACE_ROOT at a temp dir for the test
    monkeypatch.setattr("main.app.prometheus.sandbox.WORKSPACE_ROOT", tmp_path)
    return tmp_path


class TestWriteBytes:
    def test_writes_binary_content(self, workspace):
        ok = SandboxManager.write_bytes(1, "/workspace/data.bin", b"\x00\x01\x02")
        assert ok is True
        assert (workspace / "1" / "data.bin").read_bytes() == b"\x00\x01\x02"

    def test_creates_parent_dirs(self, workspace):
        ok = SandboxManager.write_bytes(1, "/workspace/reports/q1.csv", b"a,b\n")
        assert ok is True
        assert (workspace / "1" / "reports" / "q1.csv").exists()

    def test_rejects_traversal(self, workspace):
        ok = SandboxManager.write_bytes(1, "/workspace/../../evil.txt", b"x")
        assert ok is False
        assert not (workspace / "evil.txt").exists()


class TestDeleteFile:
    def test_deletes_file(self, workspace):
        (workspace / "1").mkdir(parents=True)
        (workspace / "1" / "old.csv").write_text("data")
        ok = SandboxManager.delete_file(1, "/workspace/old.csv")
        assert ok is True
        assert not (workspace / "1" / "old.csv").exists()

    def test_delete_missing_file_returns_false(self, workspace):
        (workspace / "1").mkdir(parents=True)
        assert SandboxManager.delete_file(1, "/workspace/nope.csv") is False

    def test_delete_rejects_traversal(self, workspace):
        (workspace / "1").mkdir(parents=True)
        outside = workspace / "outside.txt"
        outside.write_text("x")
        with patch("main.app.prometheus.sandbox.hostPath", side_effect=ValueError("Invalid workspace path")):
            assert SandboxManager.delete_file(1, "/workspace/../../outside.txt") is False
        assert outside.exists()
