"""Unit tests for ToolContext dataclass."""

import pytest

from main.app.prometheus.context import ToolContext
from main.app.prometheus.state import HarnessState


class TestToolContextCreation:
    def test_empty_context(self):
        ctx = ToolContext()
        assert ctx.user is None
        assert ctx.state is None
        assert ctx.sandbox is None
        assert ctx.cache is None
        assert ctx.mcpClients == {}
        assert ctx.userId is None
        assert ctx.sessionId is None

    def test_full_context(self):
        user = {"userId": 42, "username": "test", "roles": ["PREMIUM"]}
        state = HarnessState()
        state.set("key", "value")
        sandbox = object()
        cache = object()
        mcp = {"server1": object()}

        ctx = ToolContext(
            user=user,
            state=state,
            sandbox=sandbox,
            cache=cache,
            mcpClients=mcp,
            sessionId="sess-abc",
        )

        assert ctx.user is user
        assert ctx.state is state
        assert ctx.sandbox is sandbox
        assert ctx.cache is cache
        assert ctx.mcpClients is mcp
        assert ctx.sessionId == "sess-abc"

    def test_extracts_user_id_from_user_dict(self):
        user = {"userId": 99, "username": "auto"}
        ctx = ToolContext(user=user)
        assert ctx.userId == 99

    def test_user_id_override(self):
        """Explicit userId takes precedence over user dict."""
        user = {"userId": 99}
        ctx = ToolContext(user=user, userId=42)
        assert ctx.userId == 42

    def test_user_id_none_when_no_user(self):
        ctx = ToolContext(user=None)
        assert ctx.userId is None

    def test_user_id_none_when_user_has_no_id(self):
        ctx = ToolContext(user={"username": "anon"})
        assert ctx.userId is None


class TestToolContextStateAccess:
    def test_state_get(self):
        state = HarnessState()
        state.set("petr4_pe", 5.2)
        ctx = ToolContext(state=state)
        assert ctx.state.get("petr4_pe") == 5.2

    def test_state_set(self):
        state = HarnessState()
        ctx = ToolContext(state=state)
        ctx.state.set("step", "1/5")
        assert ctx.state.get("step") == "1/5"

    def test_state_to_dict(self):
        state = HarnessState()
        state.set("a", 1)
        state.set("b", 2)
        ctx = ToolContext(state=state)
        assert ctx.state.to_dict() == {"a": 1, "b": 2}


class TestToolContextMcpClients:
    def test_mcp_clients_isolation(self):
        """Two contexts share no mutable defaults."""
        ctx1 = ToolContext()
        ctx2 = ToolContext()
        ctx1.mcpClients["x"] = object()
        assert "x" not in ctx2.mcpClients

    def test_mcp_clients_passed_through(self):
        clients = {"srv1": "client1", "srv2": "client2"}
        ctx = ToolContext(mcpClients=clients)
        assert ctx.mcpClients == clients


class TestToolContextDataclass:
    def test_is_dataclass(self):
        from dataclasses import fields

        field_names = {f.name for f in fields(ToolContext)}
        assert field_names == {
            "user",
            "state",
            "sandbox",
            "cache",
            "mcpClients",
            "userId",
            "sessionId",
        }

    def test_equality(self):
        """Dataclass equality works out of the box."""
        ctx1 = ToolContext(userId=1, sessionId="a")
        ctx2 = ToolContext(userId=1, sessionId="a")
        assert ctx1 == ctx2
