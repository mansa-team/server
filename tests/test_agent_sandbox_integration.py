import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from contextlib import asynccontextmanager
from main.app.prometheus.agent import Prometheus
from main.app.prometheus.state import HarnessState


class TestAgentSandboxIntegration:
    def test_build_system_prompt_no_state(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "investments assistant" in prompt.lower()

    def test_build_system_prompt_with_state(self):
        state = HarnessState()
        state.set("current_step", "3/5")
        prompt = Prometheus.buildSystemPrompt(state=state)
        assert "[HARNESS STATE]" in prompt
        assert "- current_step: 3/5" in prompt

    def test_build_system_prompt_empty_state(self):
        state = HarnessState()
        prompt = Prometheus.buildSystemPrompt(state=state)
        assert "[HARNESS STATE]" not in prompt

    def test_system_prompt_includes_state_instructions(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "set_state" in prompt
        assert "get_state" in prompt

    def test_system_prompt_includes_sandbox_instructions(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "execute_code" in prompt

    def test_system_prompt_includes_cache_instructions(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "check_cache" in prompt

    def test_makeChat_uses_tool_registry(self):
        p = Prometheus()
        mock_session = MagicMock()
        mock_session.__deepcopy__ = lambda self, memo=None: self
        from main.app.prometheus.tools import TOOL_REGISTRY

        chat = p.makeChat([mock_session], [], system_prompt="test prompt")
        assert chat is not None

    @pytest.mark.anyio
    async def test_streamMessage_creates_loop_logger_and_cache(self):
        p = Prometheus()
        db = MagicMock()
        user = {"userId": 1, "isPremium": False}
        session = MagicMock()
        session.__deepcopy__ = lambda self, memo=None: self

        with (
            patch.object(Prometheus, "openMCPClients") as mock_open,
            patch("main.app.prometheus.agent.PrometheusChatManager") as mock_chat_mgr,
            patch("main.app.prometheus.agent.LoopLogger") as MockLoop,
            patch("main.app.prometheus.agent.ResultCache") as MockCache,
        ):
            mock_chat_mgr.getHistory.return_value = []
            mock_loop = MagicMock()
            MockLoop.return_value = mock_loop
            mock_cache = MagicMock()
            MockCache.return_value = mock_cache

            @asynccontextmanager
            async def fake_open():
                yield {"stocks": MagicMock(), "searxng": MagicMock()}, [session]

            mock_open.return_value = fake_open()

            mock_chat = MagicMock()

            async def empty_iter(msg):
                yield MagicMock(text="Hello", function_calls=None)

            async def empty_stream(msg):
                return empty_iter(msg)

            mock_chat.send_message_stream = empty_stream
            p.makeChat = MagicMock(return_value=mock_chat)

            chunks = []
            async for chunk in p.streamMessage(query="hi", sessionId="s1", db=db, user=user):
                chunks.append(chunk)

            MockLoop.assert_called_once_with(db)
            MockCache.assert_called_once()
            mock_loop.flush.assert_called_once()

    @pytest.mark.anyio
    async def test_streamMessage_premium_creates_sandbox_on_execute_code(self):
        p = Prometheus()
        db = MagicMock()
        user = {"userId": 1, "isPremium": True}
        session = MagicMock()
        session.__deepcopy__ = lambda self, memo=None: self

        with (
            patch.object(Prometheus, "openMCPClients") as mock_open,
            patch("main.app.prometheus.agent.PrometheusChatManager") as mock_chat_mgr,
            patch("main.app.prometheus.agent.LoopLogger") as MockLoop,
            patch("main.app.prometheus.agent.ResultCache") as MockCache,
            patch("main.app.prometheus.agent.SandboxManager") as MockSandbox,
            patch("main.app.prometheus.agent.dispatchToolCall") as mock_dispatch,
        ):
            mock_chat_mgr.getHistory.return_value = []
            MockLoop.return_value = MagicMock()
            MockCache.return_value = MagicMock()
            MockSandbox.create = AsyncMock(return_value="sb-1-abc")
            MockSandbox.destroy = AsyncMock()
            MockSandbox.checkpoint = AsyncMock()
            mock_dispatch.return_value = {"stdout": "42"}

            @asynccontextmanager
            async def fake_open():
                yield {"stocks": MagicMock(), "searxng": MagicMock()}, [session]

            mock_open.return_value = fake_open()

            call_count = 0

            async def exec_iter(msg):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    fc = MagicMock()
                    fc.name = "execute_code"
                    fc.args = {"code": "print(1)"}
                    yield MagicMock(text=None, function_calls=[fc])
                else:
                    yield MagicMock(text="Done", function_calls=None)

            async def streaming_fn(msg):
                return exec_iter(msg)

            mock_chat = MagicMock()
            mock_chat.send_message_stream = streaming_fn
            p.makeChat = MagicMock(return_value=mock_chat)

            chunks = []
            async for chunk in p.streamMessage(query="run code", sessionId="s1", db=db, user=user):
                chunks.append(chunk)

            MockSandbox.create.assert_called_once_with(1, "s1")
            MockSandbox.destroy.assert_called_once_with("sb-1-abc")

    @pytest.mark.anyio
    async def test_streamMessage_non_premium_blocks_sandbox(self):
        p = Prometheus()
        db = MagicMock()
        user = {"userId": 1, "isPremium": False}
        session = MagicMock()
        session.__deepcopy__ = lambda self, memo=None: self

        with (
            patch.object(Prometheus, "openMCPClients") as mock_open,
            patch("main.app.prometheus.agent.PrometheusChatManager") as mock_chat_mgr,
            patch("main.app.prometheus.agent.LoopLogger") as MockLoop,
            patch("main.app.prometheus.agent.ResultCache") as MockCache,
            patch("main.app.prometheus.agent.SandboxManager") as MockSandbox,
            patch("main.app.prometheus.agent.dispatchToolCall") as mock_dispatch,
        ):
            mock_chat_mgr.getHistory.return_value = []
            MockLoop.return_value = MagicMock()
            MockCache.return_value = MagicMock()

            @asynccontextmanager
            async def fake_open():
                yield {"stocks": MagicMock(), "searxng": MagicMock()}, [session]

            mock_open.return_value = fake_open()

            call_count = 0

            async def exec_iter(msg):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    fc = MagicMock()
                    fc.name = "execute_code"
                    fc.args = {"code": "print(1)"}
                    yield MagicMock(text=None, function_calls=[fc])
                else:
                    yield MagicMock(text="OK", function_calls=None)

            async def streaming_fn(msg):
                return exec_iter(msg)

            mock_chat = MagicMock()
            mock_chat.send_message_stream = streaming_fn
            p.makeChat = MagicMock(return_value=mock_chat)

            chunks = []
            async for chunk in p.streamMessage(query="run code", sessionId="s1", db=db, user=user):
                chunks.append(chunk)

            for call in mock_dispatch.call_args_list:
                assert call[0][0].name != "execute_code"
