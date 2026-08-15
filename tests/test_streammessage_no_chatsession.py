"""
GREEN test: streamMessage works without chatSession — MCP setup is inlined.

After refactoring, chatSession no longer exists. streamMessage uses
_createMcpClients() and _createChatSession() helpers instead.
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main.app.prometheus.agent import Prometheus


class FakeChunk:
    def __init__(self, text=None, function_calls=None):
        self.text = text
        self.function_calls = function_calls


class TestStreamMessageNoChatSession:
    """streamMessage inlines MCP setup — chatSession no longer exists."""

    @pytest.mark.anyio
    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.clientPool")
    async def test_stream_message_yields_text_chunks(self, mock_pool, mock_genai, mock_config, mock_chat):
        """streamMessage yields text chunks via inlined MCP setup."""
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []

        # Set up mock MCP pool
        mock_stocks = MagicMock()
        mock_searxng = MagicMock()
        mock_pool.clients = {"stocks": mock_stocks, "searxng": mock_searxng}
        mock_session_stocks = MagicMock()
        mock_session_searxng = MagicMock()
        mock_pool.getClients = AsyncMock(
            return_value=({"stocks": mock_stocks, "searxng": mock_searxng}, [mock_session_stocks, mock_session_searxng])
        )

        # Set up mock chat session
        async def fake_aiter():
            yield FakeChunk(text="Hello ")
            yield FakeChunk(text="world")

        mock_chat_session = MagicMock()
        mock_chat_session.send_message_stream = AsyncMock(return_value=fake_aiter())

        gen = Prometheus()
        gen.makeChat = MagicMock(return_value=mock_chat_session)
        results = []
        async for event in gen.streamMessage(query="hi", sessionId="s1", db=MagicMock()):
            results.append(event)

        assert len(results) == 2
        assert results[0] == {"type": "text", "text": "Hello "}
        assert results[1] == {"type": "text", "text": "world"}

    @pytest.mark.anyio
    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.clientPool")
    async def test_stream_message_does_not_call_chatSession(self, mock_pool, mock_genai, mock_config, mock_chat):
        """chatSession attribute must not exist — MCP setup is inlined."""
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []

        gen = Prometheus()
        # chatSession should no longer exist on the class
        assert not hasattr(gen, "chatSession")
        assert not hasattr(Prometheus, "chatSession")

    @pytest.mark.anyio
    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.clientPool")
    async def test_stream_message_handles_function_calls_without_chatsession(
        self, mock_pool, mock_genai, mock_config, mock_chat
    ):
        """streamMessage handles function call loops via inlined MCP setup."""
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []

        # Set up mock MCP pool
        mock_stocks = MagicMock()
        mock_searxng = MagicMock()
        mock_pool.clients = {"stocks": mock_stocks, "searxng": mock_searxng}
        mock_session_stocks = MagicMock()
        mock_session_searxng = MagicMock()
        mock_pool.getClients = AsyncMock(
            return_value=({"stocks": mock_stocks, "searxng": mock_searxng}, [mock_session_stocks, mock_session_searxng])
        )

        class FakeFunctionCall:
            name = "search"
            args = {"query": "test"}

        call_count = 0

        async def fake_aiter_first():
            yield FakeChunk(function_calls=[FakeFunctionCall()])

        async def fake_aiter_second():
            yield FakeChunk(text="Result: found it")

        async def fake_stream(msg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return fake_aiter_first()
            return fake_aiter_second()

        mock_chat_session = MagicMock()
        mock_chat_session.send_message_stream = AsyncMock(side_effect=fake_stream)

        gen = Prometheus()
        gen.makeChat = MagicMock(return_value=mock_chat_session)
        results = []
        async for event in gen.streamMessage(query="search test", sessionId="s2", db=MagicMock()):
            results.append(event)

        # Should have text from second stream after tool call
        assert any(e.get("text") == "Result: found it" for e in results)
        # Tool loop should have run
        assert call_count == 2

    @pytest.mark.anyio
    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.clientPool")
    async def test_user_message_saved_before_stream_error(self, mock_pool, mock_genai, mock_config, mock_chat):
        """If the stream raises on first send, the user query must already be persisted."""
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []

        mock_stocks = MagicMock()
        mock_searxng = MagicMock()
        mock_pool.clients = {"stocks": mock_stocks, "searxng": mock_searxng}
        mock_pool.getClients = AsyncMock(
            return_value=({"stocks": mock_stocks, "searxng": mock_searxng}, [MagicMock(), MagicMock()])
        )

        mock_chat_session = MagicMock()
        mock_chat_session.send_message_stream = AsyncMock(side_effect=RuntimeError("gemini down"))

        gen = Prometheus()
        gen.makeChat = MagicMock(return_value=mock_chat_session)

        db = MagicMock()
        with pytest.raises(RuntimeError):
            async for _ in gen.streamMessage(query="important question", sessionId="s-err1", db=db):
                pass

        # user turn persisted up front; no assistant text accumulated, so only one save
        mock_chat.saveMessage.assert_called_once_with(db, "s-err1", "user", "important question")

    @pytest.mark.anyio
    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.clientPool")
    async def test_partial_assistant_text_persisted_on_stream_error(
        self, mock_pool, mock_genai, mock_config, mock_chat
    ):
        """A mid-stream error must persist partial assistant text, then re-raise."""
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []

        mock_stocks = MagicMock()
        mock_searxng = MagicMock()
        mock_pool.clients = {"stocks": mock_stocks, "searxng": mock_searxng}
        mock_pool.getClients = AsyncMock(
            return_value=({"stocks": mock_stocks, "searxng": mock_searxng}, [MagicMock(), MagicMock()])
        )

        async def fake_stream_with_error(msg):
            yield FakeChunk(text="partial answer ")
            raise RuntimeError("connection lost")

        mock_chat_session = MagicMock()
        mock_chat_session.send_message_stream = AsyncMock(side_effect=fake_stream_with_error)

        gen = Prometheus()
        gen.makeChat = MagicMock(return_value=mock_chat_session)

        db = MagicMock()
        with pytest.raises(RuntimeError):
            async for _ in gen.streamMessage(query="partial question", sessionId="s-err2", db=db):
                pass

        calls = [c.args for c in mock_chat.saveMessage.call_args_list]
        assert (db, "s-err2", "user", "partial question") in calls
        assert (db, "s-err2", "assistant", "partial answer ") in calls
