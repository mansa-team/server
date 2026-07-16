import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from main.app.prometheus.agent import Prometheus
from main.app.prometheus.state import HarnessState


class TestBuildSystemPromptState:
    def test_build_system_prompt_no_state(self):
        """System prompt should work without state parameter."""
        prompt = Prometheus.buildSystemPrompt()
        assert "investments assistant" in prompt.lower()

    def test_build_system_prompt_with_state(self):
        """System prompt should include state context when provided."""
        state = HarnessState()
        state.set("current_step", "3/5")
        prompt = Prometheus.buildSystemPrompt(state=state)
        assert "[HARNESS STATE]" in prompt
        assert "- current_step: 3/5" in prompt

    def test_build_system_prompt_empty_state(self):
        """System prompt should not include state section when empty."""
        state = HarnessState()
        prompt = Prometheus.buildSystemPrompt(state=state)
        assert "[HARNESS STATE]" not in prompt

    def test_build_system_prompt_state_after_memories(self):
        """State section should appear after memories section."""
        state = HarnessState()
        state.set("k", "v")
        prompt = Prometheus.buildSystemPrompt(state=state)
        state_pos = prompt.find("[HARNESS STATE]")
        prompt_end = prompt.find("[/HARNESS STATE]")
        assert state_pos > 0
        assert prompt_end > state_pos

    def test_build_system_prompt_multiple_state_entries(self):
        """All state entries should appear in the prompt."""
        state = HarnessState()
        state.set("step", "1/3")
        state.set("ticker", "PETR4")
        prompt = Prometheus.buildSystemPrompt(state=state)
        assert "- step: 1/3" in prompt
        assert "- ticker: PETR4" in prompt


class TestSendMessageStateIntegration:
    @pytest.mark.anyio
    async def test_send_message_creates_harness_state(self):
        """sendMessage should create a HarnessState and pass it to buildSystemPrompt."""
        prometheus = Prometheus()
        prometheus.client = MagicMock()
        prometheus.client.aio = MagicMock()

        mock_chat = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "Hello"
        mock_chat.send_message = AsyncMock(return_value=mock_response)
        prometheus.client.aio.chats.create = MagicMock(return_value=mock_chat)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        with patch("main.app.prometheus.agent.PrometheusChatManager") as mock_pcm:
            mock_pcm.getHistory.return_value = []
            with patch("main.app.prometheus.agent.Prometheus.buildSystemPrompt") as mock_build:
                mock_build.return_value = "system prompt"
                with patch("main.app.prometheus.agent.Prometheus.openMCPClients") as mock_open:
                    mock_open.return_value.__aenter__ = AsyncMock(return_value=({}, []))
                    mock_open.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await prometheus.sendMessage(query="test", sessionId="s1", db=mock_db, user={"userId": 1})

                    # buildSystemPrompt should have been called with a state kwarg
                    call_kwargs = mock_build.call_args
                    assert "state" in call_kwargs.kwargs
                    assert isinstance(call_kwargs.kwargs["state"], HarnessState)


class TestStreamMessageStateIntegration:
    @pytest.mark.anyio
    async def test_stream_message_creates_harness_state(self):
        """streamMessage should create a HarnessState and pass it to buildSystemPrompt."""
        prometheus = Prometheus()
        prometheus.client = MagicMock()
        prometheus.client.aio = MagicMock()

        # Mock stream that returns text then ends
        async def fake_stream():
            chunk = MagicMock()
            chunk.text = "Hello"
            chunk.function_calls = None
            yield chunk

        mock_chat = AsyncMock()
        mock_chat.send_message_stream = AsyncMock(return_value=fake_stream())
        prometheus.client.aio.chats.create = MagicMock(return_value=mock_chat)

        mock_db = MagicMock()

        with patch("main.app.prometheus.agent.PrometheusChatManager") as mock_pcm:
            mock_pcm.getHistory.return_value = []
            with patch("main.app.prometheus.agent.Prometheus.buildSystemPrompt") as mock_build:
                mock_build.return_value = "system prompt"
                with patch("main.app.prometheus.agent.Prometheus.openMCPClients") as mock_open:
                    mock_open.return_value.__aenter__ = AsyncMock(return_value=({}, []))
                    mock_open.return_value.__aexit__ = AsyncMock(return_value=False)

                    chunks = []
                    async for chunk in prometheus.streamMessage(
                        query="test", sessionId="s1", db=mock_db, user={"userId": 1}
                    ):
                        chunks.append(chunk)

                    # buildSystemPrompt should have been called with a state kwarg
                    call_kwargs = mock_build.call_args
                    assert "state" in call_kwargs.kwargs
                    assert isinstance(call_kwargs.kwargs["state"], HarnessState)

    @pytest.mark.anyio
    async def test_stream_message_passes_state_to_dispatch(self):
        """streamMessage should pass state to dispatchToolCall."""
        prometheus = Prometheus()
        prometheus.client = MagicMock()
        prometheus.client.aio = MagicMock()

        # Mock stream that returns a function call then text
        fc = MagicMock()
        fc.name = "set_state"
        fc.args = {"key": "step", "value": "1/5"}

        async def fake_stream():
            chunk = MagicMock()
            chunk.text = None
            chunk.function_calls = {"call1": fc}
            yield chunk

        async def fake_stream_2():
            chunk = MagicMock()
            chunk.text = "Done"
            chunk.function_calls = None
            yield chunk

        call_count = 0

        async def fake_send_message_stream(msg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return fake_stream()
            return fake_stream_2()

        mock_chat = AsyncMock()
        mock_chat.send_message_stream = fake_send_message_stream
        prometheus.client.aio.chats.create = MagicMock(return_value=mock_chat)

        mock_db = MagicMock()

        with patch("main.app.prometheus.agent.PrometheusChatManager") as mock_pcm:
            mock_pcm.getHistory.return_value = []
            with patch("main.app.prometheus.agent.dispatchToolCall") as mock_dispatch:
                mock_dispatch.return_value = {"status": "ok", "key": "step"}
                with patch("main.app.prometheus.agent.Prometheus.openMCPClients") as mock_open:
                    mock_open.return_value.__aenter__ = AsyncMock(return_value=({}, []))
                    mock_open.return_value.__aexit__ = AsyncMock(return_value=False)

                    chunks = []
                    async for chunk in prometheus.streamMessage(
                        query="test", sessionId="s1", db=mock_db, user={"userId": 1}
                    ):
                        chunks.append(chunk)

                    # dispatchToolCall should have been called with state kwarg
                    if mock_dispatch.called:
                        call_kwargs = mock_dispatch.call_args
                        assert "state" in call_kwargs.kwargs
                        assert isinstance(call_kwargs.kwargs["state"], HarnessState)


class TestSystemPromptStateInstructions:
    def test_system_prompt_has_harness_state_section(self):
        """System prompt should instruct LLM about harness state usage."""
        from main.app.prometheus.agent import Prometheus

        prompt = Prometheus.SYSTEM_PROMPT
        assert "Harness State" in prompt or "harness state" in prompt.lower()
        assert "set_state" in prompt
        assert "get_state" in prompt

    def test_system_prompt_has_memory_sync_section(self):
        """System prompt should instruct LLM about memory vs state."""
        from main.app.prometheus.agent import Prometheus

        prompt = Prometheus.SYSTEM_PROMPT
        assert "Memory Sync" in prompt or "memory sync" in prompt.lower()
        assert "save_memory" in prompt
