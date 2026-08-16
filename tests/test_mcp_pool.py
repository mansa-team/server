import asyncio
import copy
import time

from unittest.mock import ANY, AsyncMock, patch

import main.app.prometheus.mcp as mcp
from main.app.prometheus.mcp import MCPClientPool, clientPool


class TestMCPClientPool:
    def test_module_level_instance_is_shared(self):
        assert isinstance(clientPool, MCPClientPool)
        assert clientPool is not None

    def test_new_instances_are_distinct(self):
        p1 = MCPClientPool()
        p2 = MCPClientPool()
        assert p1 is not p2

    def test_not_initialized(self):
        pool = MCPClientPool()
        pool.clients = None
        assert pool.clients is None


class _FakeSession:
    """Deterministic stand-in for a fastmcp client session."""

    def __init__(self, tools_error=None):
        self.tools_error = tools_error
        self.tools_calls = 0

    async def list_tools(self):
        self.tools_calls += 1
        if self.tools_error is not None:
            raise self.tools_error
        return ["tools"]


class _FakeClient:
    """Deterministic stand-in for a fastmcp Client with async enter/exit."""

    def __init__(self, name="fake", session=None, aenter_error=None, aexit_error=None):
        self.name = name
        self.session = session if session is not None else _FakeSession()
        self.aenter_error = aenter_error
        self.aexit_error = aexit_error
        self.entered = 0
        self.exited = 0

    async def __aenter__(self):
        self.entered += 1
        if self.aenter_error is not None:
            raise self.aenter_error
        return self

    async def __aexit__(self, *args):
        self.exited += 1
        if self.aexit_error is not None:
            raise self.aexit_error


async def _getClientsAndYield(pool):
    result = await pool.getClients()
    await asyncio.sleep(0)  # let a scheduled healthCheck task complete
    return result


async def _runHealthCheckTwice(pool):
    await asyncio.gather(pool.healthCheck(), pool.healthCheck())


class TestBuildClient:
    def test_with_headers_builds_streamable_transport(self):
        server = {"name": "stocks", "url": "http://host:8000/stocks/mcp", "headers": {"X-MCP": "true"}}
        with patch.object(mcp, "Client") as mock_client, patch.object(mcp, "StreamableHttpTransport") as mock_transport:
            result = mcp.buildClient(server)
        mock_transport.assert_called_once_with("http://host:8000/stocks/mcp", headers={"X-MCP": "true"})
        mock_client.assert_called_once_with(transport=mock_transport.return_value)
        assert result is mock_client.return_value

    def test_without_headers_builds_plain_url(self):
        server = {"name": "searxng", "url": "http://searxng:8080/mcp/"}
        with patch.object(mcp, "Client") as mock_client, patch.object(mcp, "StreamableHttpTransport") as mock_transport:
            result = mcp.buildClient(server)
        mock_client.assert_called_once_with("http://searxng:8080/mcp/")
        mock_transport.assert_not_called()
        assert result is mock_client.return_value


class TestInitialize:
    def test_connects_all_servers(self):
        fakes = {name: _FakeClient(name) for name in ("stocks", "searxng")}
        pool = MCPClientPool()
        with (
            patch.object(mcp, "buildClient", side_effect=lambda s: fakes[s["name"]]),
            patch.object(mcp, "logger") as mock_logger,
        ):
            asyncio.run(pool.initialize())
        assert set(pool.clients) == {"stocks", "searxng"}
        assert pool.clients["stocks"] is fakes["stocks"]
        assert pool.clients["searxng"] is fakes["searxng"]
        assert all(c.entered == 1 for c in fakes.values())
        assert pool.lastHealthCheck > 0
        # deepcopy monkeypatch applied to session types without raising
        assert copy.deepcopy(fakes["stocks"].session) is fakes["stocks"].session
        mock_logger.info.assert_any_call("MCPClientPool: initialized with %s", ["stocks", "searxng"])

    def test_continues_on_connect_error(self):
        bad = _FakeClient("stocks", aenter_error=RuntimeError("boom"))
        good = _FakeClient("searxng")
        fakes = {"stocks": bad, "searxng": good}
        pool = MCPClientPool()
        with (
            patch.object(mcp, "buildClient", side_effect=lambda s: fakes[s["name"]]),
            patch.object(mcp, "logger") as mock_logger,
        ):
            asyncio.run(pool.initialize())
        assert "stocks" not in pool.clients
        assert pool.clients["searxng"] is good
        assert pool.lastHealthCheck > 0
        mock_logger.error.assert_called_once_with("MCPClientPool: %s connect failed: %s", "stocks", ANY)


class TestGetClients:
    def test_initializes_when_clients_none(self):
        pool = MCPClientPool()
        pool.clients = None
        fake = _FakeClient("stocks")

        async def _initialize():
            pool.clients = {"stocks": fake}
            pool.lastHealthCheck = time.time()

        with (
            patch.object(pool, "initialize", new=AsyncMock(side_effect=_initialize)) as mock_init,
            patch.object(pool, "healthCheck", new=AsyncMock()) as mock_hc,
        ):
            clients, sessions = asyncio.run(pool.getClients())
        mock_init.assert_awaited_once()
        mock_hc.assert_not_awaited()
        assert clients == {"stocks": fake}
        assert sessions == [fake.session]

    def test_no_health_check_when_interval_fresh(self):
        pool = MCPClientPool()
        fake = _FakeClient("stocks")
        pool.clients = {"stocks": fake}
        pool.lastHealthCheck = time.time()
        with patch.object(pool, "healthCheck", new=AsyncMock()) as mock_hc:
            clients, sessions = asyncio.run(pool.getClients())
        mock_hc.assert_not_awaited()
        assert clients == {"stocks": fake}
        assert sessions == [fake.session]

    def test_schedules_health_check_when_interval_elapsed(self):
        pool = MCPClientPool()
        fake = _FakeClient("stocks")
        pool.clients = {"stocks": fake}
        pool.lastHealthCheck = 0.0
        with patch.object(pool, "healthCheck", new=AsyncMock()) as mock_hc:
            clients, sessions = asyncio.run(_getClientsAndYield(pool))
        mock_hc.assert_awaited_once()
        assert clients == {"stocks": fake}
        assert sessions == [fake.session]


class TestHealthCheck:
    def test_returns_early_when_recently_checked(self):
        pool = MCPClientPool()
        fake = _FakeClient("stocks")
        pool.clients = {"stocks": fake}
        pool.lastHealthCheck = time.time()
        with patch.object(pool, "reconnect", new=AsyncMock()) as mock_reconnect:
            asyncio.run(pool.healthCheck())
        assert fake.session.tools_calls == 0
        mock_reconnect.assert_not_awaited()

    def test_double_check_guard_skips_second_call(self):
        pool = MCPClientPool()
        fake = _FakeClient("stocks")
        pool.clients = {"stocks": fake}
        pool.lastHealthCheck = 0.0
        with patch.object(pool, "reconnect", new=AsyncMock()) as mock_reconnect:
            asyncio.run(_runHealthCheckTwice(pool))
        assert fake.session.tools_calls == 1  # only the first call ran the tool check
        mock_reconnect.assert_not_awaited()

    def test_all_healthy_no_reconnect(self):
        pool = MCPClientPool()
        s1, s2 = _FakeClient("stocks"), _FakeClient("searxng")
        pool.clients = {"stocks": s1, "searxng": s2}
        pool.lastHealthCheck = 0.0
        with patch.object(pool, "reconnect", new=AsyncMock()) as mock_reconnect:
            asyncio.run(pool.healthCheck())
        assert s1.session.tools_calls == 1
        assert s2.session.tools_calls == 1
        mock_reconnect.assert_not_awaited()
        assert pool.lastHealthCheck > 0

    def test_unhealthy_reconnects(self):
        pool = MCPClientPool()
        good = _FakeClient("stocks")
        bad = _FakeClient("searxng", session=_FakeSession(tools_error=RuntimeError("timeout")))
        pool.clients = {"stocks": good, "searxng": bad}
        pool.lastHealthCheck = 0.0
        with (
            patch.object(pool, "reconnect", new=AsyncMock()) as mock_reconnect,
            patch.object(mcp, "logger") as mock_logger,
        ):
            asyncio.run(pool.healthCheck())
        assert good.session.tools_calls == 1
        assert bad.session.tools_calls == 1
        mock_reconnect.assert_awaited_once_with("searxng")
        mock_logger.warning.assert_called_once_with("MCPClientPool: %s unhealthy, reconnecting: %s", "searxng", ANY)


class TestReconnect:
    def test_unknown_server_logs_error(self):
        pool = MCPClientPool()
        fake = _FakeClient("stocks")
        pool.clients = {"stocks": fake}
        with patch.object(mcp, "buildClient") as mock_build, patch.object(mcp, "logger") as mock_logger:
            asyncio.run(pool.reconnect("ghost"))
        mock_build.assert_not_called()
        mock_logger.error.assert_called_once_with("MCPClientPool: %s not found in MCP_SERVERS", "ghost")
        assert pool.clients == {"stocks": fake}
        assert fake.exited == 0

    def test_replaces_existing_client(self):
        pool = MCPClientPool()
        old = _FakeClient("stocks")
        new = _FakeClient("stocks")
        pool.clients = {"stocks": old}
        server = mcp.MCP_SERVERS[0]
        with (
            patch.object(mcp, "buildClient", return_value=new) as mock_build,
            patch.object(mcp, "logger") as mock_logger,
        ):
            asyncio.run(pool.reconnect("stocks"))
        assert old.exited == 1
        assert new.entered == 1
        assert pool.clients["stocks"] is new
        mock_build.assert_called_once_with(server)
        mock_logger.info.assert_called_once_with("MCPClientPool: %s reconnected", "stocks")

    def test_adds_missing_client(self):
        pool = MCPClientPool()
        new = _FakeClient("searxng")
        pool.clients = {}
        with patch.object(mcp, "buildClient", return_value=new) as mock_build:
            asyncio.run(pool.reconnect("searxng"))
        assert pool.clients["searxng"] is new
        assert new.entered == 1
        mock_build.assert_called_once()

    def test_build_error_keeps_old_client(self):
        pool = MCPClientPool()
        old = _FakeClient("stocks")
        bad = _FakeClient("stocks", aenter_error=RuntimeError("boom"))
        pool.clients = {"stocks": old}
        with (
            patch.object(mcp, "buildClient", return_value=bad) as mock_build,
            patch.object(mcp, "logger") as mock_logger,
        ):
            asyncio.run(pool.reconnect("stocks"))
        assert old.exited == 1  # old client torn down before the failed rebuild
        assert pool.clients["stocks"] is old
        mock_build.assert_called_once()
        mock_logger.error.assert_called_once_with("MCPClientPool: %s reconnect failed: %s", "stocks", ANY)


class TestClose:
    def test_exits_all_clients(self):
        pool = MCPClientPool()
        f1, f2 = _FakeClient("stocks"), _FakeClient("searxng")
        pool.clients = {"stocks": f1, "searxng": f2}
        asyncio.run(pool.close())
        assert f1.exited == 1
        assert f2.exited == 1
        assert pool.clients is None

    def test_swallows_exit_errors(self):
        pool = MCPClientPool()
        f1 = _FakeClient("stocks", aexit_error=RuntimeError("boom"))
        f2 = _FakeClient("searxng")
        pool.clients = {"stocks": f1, "searxng": f2}
        asyncio.run(pool.close())
        assert f1.exited == 1
        assert f2.exited == 1
        assert pool.clients is None

    def test_noop_when_no_clients(self):
        pool = MCPClientPool()
        pool.clients = None
        asyncio.run(pool.close())
        assert pool.clients is None
