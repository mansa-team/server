"""Unit tests for SandboxManager — HTTP calls mocked via a fake client class."""

import pytest
from unittest.mock import patch, MagicMock

from main.app.prometheus.sandbox import SandboxManager


class _FakeClient:
    """Fake httpx.AsyncClient that records calls and returns pre-set responses."""

    def __init__(self, base_url="", timeout=None):
        self.calls: list[tuple[str, tuple, dict]] = []
        self._responses: dict[str, MagicMock] = {}

    def set_response(self, method: str, resp: MagicMock):
        self._responses[method] = resp

    async def post(self, url, **kw):
        self.calls.append(("post", (url,), kw))
        return self._responses.get("post", MagicMock())

    async def get(self, url, **kw):
        self.calls.append(("get", (url,), kw))
        return self._responses.get("get", MagicMock())

    async def put(self, url, **kw):
        self.calls.append(("put", (url,), kw))
        return self._responses.get("put", MagicMock())

    async def delete(self, url, **kw):
        self.calls.append(("delete", (url,), kw))
        return self._responses.get("delete", MagicMock())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _ok_response(json_data=None, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    r.raise_for_status = lambda: None
    return r


class TestSandboxCreate:
    @pytest.mark.asyncio
    async def test_create_returns_sandbox_id(self):
        fc = _FakeClient()
        fc.set_response("post", _ok_response({"sandboxId": "sb-1-abc12345"}))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.create(1, "sess-1")
            assert result == "sb-1-abc12345"

    @pytest.mark.asyncio
    async def test_create_fallback_id_on_empty_response(self):
        fc = _FakeClient()
        fc.set_response("post", _ok_response({}))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.create(42, "sess-2")
            assert result.startswith("sb-42-")


class TestSandboxExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_stdout_stderr(self):
        fc = _FakeClient()
        fc.set_response("post", _ok_response({"stdout": "hello\n", "stderr": ""}))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.execute("sb-1-abc", "print('hello')")
            assert result["stdout"] == "hello\n"
            assert result["stderr"] == ""

    @pytest.mark.asyncio
    async def test_execute_sends_code_in_body(self):
        fc = _FakeClient()
        fc.set_response("post", _ok_response({"stdout": "", "stderr": ""}))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            await SandboxManager.execute("sb-1-abc", "x = 1")
            assert fc.calls[0] == ("post", ("/sandboxes/sb-1-abc/executions",), {"json": {"code": "x = 1"}})


class TestSandboxCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_returns_checkpoint_id(self):
        fc = _FakeClient()
        fc.set_response("post", _ok_response({"checkpointId": "cp-abc12345"}))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.checkpoint("sb-1-abc", "my-key")
            assert result == "cp-abc12345"


class TestSandboxRestore:
    @pytest.mark.asyncio
    async def test_restore_returns_new_sandbox_id(self):
        fc = _FakeClient()
        fc.set_response("post", _ok_response({"sandboxId": "sb-new-id"}))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.restore("cp-abc")
            assert result == "sb-new-id"


class TestSandboxUploadFile:
    @pytest.mark.asyncio
    async def test_upload_file_returns_true_on_success(self):
        fc = _FakeClient()
        fc.set_response("put", _ok_response(status=200))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.upload_file("sb-1-abc", "/data.csv", b"col1,col2")
            assert result is True

    @pytest.mark.asyncio
    async def test_upload_file_returns_false_on_error(self):
        fc = _FakeClient()
        fc.set_response("put", _ok_response(status=500))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.upload_file("sb-1-abc", "/data.csv", b"bad")
            assert result is False


class TestSandboxReadFile:
    @pytest.mark.asyncio
    async def test_read_file_returns_content(self):
        fc = _FakeClient()
        fc.set_response("get", _ok_response({"content": "file contents here"}))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            result = await SandboxManager.read_file("sb-1-abc", "/output.txt")
            assert result == "file contents here"


class TestSandboxDestroy:
    @pytest.mark.asyncio
    async def test_destroy_calls_delete(self):
        fc = _FakeClient()
        fc.set_response("delete", _ok_response(status=204))
        with patch("main.app.prometheus.sandbox.httpx.AsyncClient", return_value=fc):
            await SandboxManager.destroy("sb-1-abc")
            assert fc.calls[0] == ("delete", ("/sandboxes/sb-1-abc",), {})
