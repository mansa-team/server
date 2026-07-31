import pytest
from unittest.mock import patch, AsyncMock
from main.app.prometheus.mcp import MCPClientPool


class TestMCPClientPool:
    def test_singleton(self):
        p1 = MCPClientPool()
        p2 = MCPClientPool()
        assert p1 is p2

    def test_not_initialized(self):
        pool = MCPClientPool()
        pool.clients = None
        assert pool.clients is None
