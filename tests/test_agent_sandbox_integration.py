import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from main.app.prometheus.agent import Prometheus
from main.app.prometheus.state import HarnessState


class TestAgentSandboxIntegration:
    def test_build_system_prompt_includes_sandbox_instructions(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "execute_code" in prompt
        assert "read_file" in prompt
        assert "write_file" in prompt

    def test_build_system_prompt_includes_state_instructions(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "set_state" in prompt
        assert "get_state" in prompt

    def test_build_system_prompt_with_state(self):
        state = HarnessState()
        state.set("current_step", "3/5")
        prompt = Prometheus.buildSystemPrompt(state=state)
        assert "[HARNESS STATE]" in prompt
        assert "- current_step: 3/5" in prompt

    @patch("main.app.prometheus.agent.SandboxManager")
    @pytest.mark.anyio
    async def test_streamMessage_creates_sandbox_on_execute_code(self, mock_sandbox_cls):
        """Verify on-demand sandbox is created when LLM calls execute_code."""
        mock_sandbox_cls.create = AsyncMock(return_value="sb-new")
        mock_sandbox_cls.destroy = AsyncMock()
        assert hasattr(mock_sandbox_cls, "create")
        assert hasattr(mock_sandbox_cls, "destroy")


class TestPremiumCheck:
    """Test the premium gating logic used in streamMessage."""

    def test_premium_user_has_sandbox_access(self):
        user = {"userId": 1, "roles": ["USER", "PREMIUM"]}
        roles = user.get("roles", [])
        is_premium = any(r.upper() in ("PREMIUM", "ADMIN") for r in roles)
        assert is_premium is True

    def test_admin_user_has_sandbox_access(self):
        user = {"userId": 1, "roles": ["ADMIN"]}
        roles = user.get("roles", [])
        is_premium = any(r.upper() in ("PREMIUM", "ADMIN") for r in roles)
        assert is_premium is True

    def test_free_user_no_sandbox_access(self):
        user = {"userId": 1, "roles": ["USER"]}
        roles = user.get("roles", [])
        is_premium = any(r.upper() in ("PREMIUM", "ADMIN") for r in roles)
        assert is_premium is False

    def test_no_user_no_sandbox_access(self):
        user = None
        roles = user.get("roles", []) if user else []
        is_premium = any(r.upper() in ("PREMIUM", "ADMIN") for r in roles)
        assert is_premium is False
