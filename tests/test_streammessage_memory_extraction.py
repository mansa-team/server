import sys
import time
import types
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import getSession
from main.models.base import Base
from main.models.prometheus import PrometheusSession


@pytest.fixture(autouse=True)
def stubFastmcp():
    # fastmcp client import is broken in this env (mcp SDK version mismatch:
    # fastmcp 3.3.1 expects `from mcp import McpError`, installed mcp exports MCPError).
    # Stub fastmcp so main.app.prometheus.agent imports; real MCP pool never runs.
    fastmcpStub = types.ModuleType("fastmcp")
    fastmcpStub.Client = MagicMock()
    clientStub = types.ModuleType("fastmcp.client")
    clientClientStub = types.ModuleType("fastmcp.client.client")
    clientClientStub.StreamableHttpTransport = MagicMock()
    originals = {name: sys.modules.get(name) for name in ("fastmcp", "fastmcp.client", "fastmcp.client.client")}
    sys.modules["fastmcp"] = fastmcpStub
    sys.modules["fastmcp.client"] = clientStub
    sys.modules["fastmcp.client.client"] = clientClientStub
    yield
    for name, original in originals.items():
        if original is not None:
            sys.modules[name] = original
        else:
            sys.modules.pop(name, None)


def test_streammessage_triggers_memory_extraction(client):
    # Shared in-memory sqlite with StaticPool so the TestClient portal thread
    # sees the same DB as the test thread (plain :memory: is per-connection).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    dbSession = sessionmaker(bind=engine)()
    dbSession.add(PrometheusSession(sessionId="s1", userId=1, title="Test", summary="", history=[]))
    dbSession.commit()
    client.app.dependency_overrides[getSession] = lambda: dbSession

    class FakeChunk:
        def __init__(self):
            self.text = "ok"
            self.function_calls = None

    async def fakeStream():
        yield FakeChunk()

    mockChatSession = AsyncMock()
    mockChatSession.send_message_stream = AsyncMock(return_value=fakeStream())

    with (
        patch("main.app.prometheus.agent.clientPool") as mockPool,
        patch("main.app.prometheus.agent.Config") as mockConfig,
        patch("main.app.prometheus.agent.genai"),
        patch("main.app.prometheus.agent.PrometheusCompactor"),
        patch("main.app.prometheus.agent.Prometheus.makeChat", return_value=mockChatSession),
        patch("main.app.prometheus.memory.PrometheusMemory.extract") as mockExtract,
    ):
        mockConfig.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        mockConfig.DEBUG_MODE = True
        mockConfig.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mockPool.clients = {"stocks": MagicMock()}
        mockPool.getClients = AsyncMock(return_value=({"stocks": MagicMock()}, [MagicMock()]))

        resp = client.post(
            "/prometheus/chat/stream",
            json={"query": "lembre que prefiro FIIs", "sessionId": "s1"},
        )
        assert resp.status_code == 200

    time.sleep(0.3)  # extraction runs in a background thread, give the executor a beat

    assert mockExtract.call_count == 1
    assert mockExtract.call_args.args[1] == 1
    assert mockExtract.call_args.args[2] == "s1"
    assert mockExtract.call_args.args[3] == ["PREMIUM"]
