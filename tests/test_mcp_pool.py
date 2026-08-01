import pytest
from unittest.mock import patch, AsyncMock
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
