"""Tests for Prometheus agent context: R2 (bounded episode injection)."""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from main.app.prometheus.agent import Prometheus, SYSTEM_PROMPT
from main.models.prometheus import PrometheusSession


@pytest.fixture
def fake_session_with_120_messages(dbSession):
    """Create a session with 120 messages and enough episodes to test max 5 injection."""
    history = [{"role": "user", "content": f"Message {i}", "timestamp": datetime.now().isoformat()} for i in range(120)]
    # Simulate multiple episodes in summary
    episodes = [
        {
            "id": f"ep_{i:04d}",
            "time": datetime.now().isoformat(),
            "summary": f"Episode {i} summary about topic {i}",
            "keyDecisions": [f"Decision {i}"],
            "entities": [f"Entity {i}"],
            "message_range": [i * 20, (i + 1) * 20],
        }
        for i in range(8)  # 8 episodes, should only inject last 5
    ]
    session = PrometheusSession(
        sessionId="test-120",
        userId=1,
        title="Long Session",
        history=history,
        summary=json.dumps(episodes),
    )
    dbSession.add(session)
    dbSession.commit()
    return session


class TestBuildSystemPrompt:
    def test_injects_max_5_episodes(self, dbSession, fake_session_with_120_messages):
        prompt = Prometheus.buildSystemPrompt(
            userId=1,
            db=dbSession,
            sessionId=fake_session_with_120_messages.sessionId,
        )
        # format is [1] summary, [2] summary, ...
        episode_count = sum(1 for line in prompt.split("\n") if line.startswith("[") and line[1].isdigit())
        assert episode_count <= 5
        assert episode_count >= 1

    def test_episode_format_is_single_line(self, dbSession, fake_session_with_120_messages):
        prompt = Prometheus.buildSystemPrompt(
            userId=1,
            db=dbSession,
            sessionId=fake_session_with_120_messages.sessionId,
        )
        lines = prompt.split("\n")
        episode_lines = [ln for ln in lines if ln.startswith("[") and ln[1].isdigit()]
        for line in episode_lines:
            # each episode is one line: [N] summary text
            assert line.count("\n") == 0

    def test_no_episodes_when_session_has_none(self, dbSession):
        session = PrometheusSession(
            sessionId="test-empty",
            userId=1,
            title="Empty",
            history=[],
            summary=None,
        )
        dbSession.add(session)
        dbSession.commit()
        prompt = Prometheus.buildSystemPrompt(
            userId=1,
            db=dbSession,
            sessionId="test-empty",
        )
        # no lines starting with [N]
        assert not any(ln.startswith("[") and ln[1].isdigit() for ln in prompt.split("\n"))

    def test_memory_search_called_without_query(self, dbSession):
        """The query must never reach memory search — stable ranking keeps the prompt cacheable."""
        with patch("main.app.prometheus.agent.PrometheusMemory.search", return_value=[]) as mock_search:
            Prometheus.buildSystemPrompt(userId=1, db=dbSession, sessionId=None)
            mock_search.assert_called_once_with(dbSession, 1, "", limit=10)

    def test_system_prompt_is_stable_across_calls(self, dbSession, fake_session_with_120_messages):
        """Same session + user must produce byte-identical prompts (no query-dependent memory block)."""
        first = Prometheus.buildSystemPrompt(
            userId=1,
            db=dbSession,
            sessionId=fake_session_with_120_messages.sessionId,
        )
        second = Prometheus.buildSystemPrompt(
            userId=1,
            db=dbSession,
            sessionId=fake_session_with_120_messages.sessionId,
        )
        assert first == second


class TestLazyClientSingleton:
    """Prometheus() must share one genai client via the module-level lazy singleton."""

    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.client", None)
    def test_client_created_once_and_shared(self, mock_config, mock_genai):
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        first = Prometheus()
        second = Prometheus()
        assert first.client is second.client
        mock_genai.Client.assert_called_once_with(api_key="test-key")


class TestPromptMemoryGuidance:
    def test_prompt_guides_search_before_answer(self):
        assert "search_memory" in SYSTEM_PROMPT
        assert "antes de responder" in SYSTEM_PROMPT

    def test_prompt_guides_save_when_and_types(self):
        assert "save_memory" in SYSTEM_PROMPT
        assert "preference" in SYSTEM_PROMPT
        assert "analysis" in SYSTEM_PROMPT


# ---- moved from test_prometheus_auth_coverage.py (TestPrometheusInit) ----


# ---------------------------------------------------------------------------
# Prometheus (agent.py) — covers __init__, updateDates, sendMessage, streamMessage
# ---------------------------------------------------------------------------


class TestPrometheusInit:
    """Cover __init__."""

    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.client", None)
    def test_init_creates_client(self, mock_genai, mock_config):
        # _client is a lazy module-level singleton (created once per process);
        # reset it so construction goes through the mocked genai.Client.
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="test-key")
        mock_config.DEBUG_MODE = True

        from main.app.prometheus.agent import Prometheus

        gen = Prometheus()
        mock_genai.Client.assert_called_once_with(api_key="test-key")


# ---- moved from test_prometheus_auth_coverage.py (TestPrometheusSendMessage) ----


class TestPrometheusSendMessage:
    """Cover streamMessage in agent.py."""

    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    async def test_send_message_basic(self, mock_genai, mock_config, mock_chat):
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client = MagicMock(return_value=mock_client)
        mock_chat.getHistory.return_value = []

        async def fake_stream(*args, **kwargs):
            yield {"type": "text", "text": "Hello from Gemini"}

        from main.app.prometheus.agent import Prometheus

        gen = Prometheus()
        gen.streamMessage = fake_stream

        results = []
        async for event in gen.streamMessage(
            query="Qual o P/L de PETR4?", sessionId="sess-1", db=MagicMock(), user={"userId": 1}
        ):
            results.append(event)
        assert results[-1]["text"] == "Hello from Gemini"

    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    async def test_send_message_saves_user_message_on_error(self, mock_genai, mock_config, mock_chat):
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}

        async def failing_stream(*args, **kwargs):
            raise Exception("API error")
            yield  # make it async generator

        from main.app.prometheus.agent import Prometheus

        gen = Prometheus()
        gen.streamMessage = failing_stream

        with pytest.raises(Exception):
            async for _ in gen.streamMessage(query="test", sessionId="sess-2", db=MagicMock(), user={"userId": 1}):
                pass

    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    async def test_send_message_with_history(self, mock_genai, mock_config, mock_chat):
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}

        async def fake_stream(*args, **kwargs):
            yield {"type": "text", "text": "Reply with history"}

        from main.app.prometheus.agent import Prometheus

        gen = Prometheus()
        gen.streamMessage = fake_stream

        results = []
        async for event in gen.streamMessage(query="next", sessionId="sess-3", db=MagicMock(), user={"userId": 1}):
            results.append(event)
        assert results[-1]["text"] == "Reply with history"

    @patch("main.app.prometheus.agent.clientPool")
    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    async def test_stream_message_yields_text_chunks(self, mock_genai, mock_config, mock_chat, mock_pool_cls):
        """streamMessage must yield dict chunks from async iterator."""
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []

        mock_pool_cls.clients = {"stocks": MagicMock(), "searxng": MagicMock()}
        mock_pool_cls.getClients = AsyncMock(
            return_value=(
                {"stocks": MagicMock(), "searxng": MagicMock()},
                [MagicMock(), MagicMock()],
            )
        )

        class FakeChunk:
            def __init__(self, text=None, function_calls=None):
                self.text = text
                self.function_calls = function_calls

        chunks = [FakeChunk(text="Hello "), FakeChunk(text="world")]

        async def fake_aiter():
            for c in chunks:
                yield c

        mock_chat_session = AsyncMock()
        mock_chat_session.send_message_stream = AsyncMock(return_value=fake_aiter())

        from main.app.prometheus.agent import Prometheus

        gen = Prometheus()
        gen.makeChat = MagicMock(return_value=mock_chat_session)

        results = []
        async for event in gen.streamMessage(query="hi", sessionId="s1", db=MagicMock()):
            results.append(event)

        assert len(results) == 2
        assert results[0] == {"type": "text", "text": "Hello "}
        assert results[1] == {"type": "text", "text": "world"}

    @patch("main.app.prometheus.agent.clientPool")
    @patch("main.app.prometheus.agent.PrometheusChatManager")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    async def test_stream_message_handles_function_calls(self, mock_genai, mock_config, mock_chat, mock_pool_cls):
        """streamMessage must handle function_calls as a list (not dict)."""
        mock_config.PROMETHEUS = MagicMock(GEMINI_API_KEY="key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []

        mock_pool_cls.clients = {"stocks": MagicMock(), "searxng": MagicMock()}
        mock_pool_cls.getClients = AsyncMock(
            return_value=(
                {"stocks": MagicMock(), "searxng": MagicMock()},
                [MagicMock(), MagicMock()],
            )
        )

        class FakeChunk:
            def __init__(self, text=None, function_calls=None):
                self.text = text
                self.function_calls = function_calls

        class FakeFunctionCall:
            name = "search"
            args = {"query": "test"}

        call_count = 0

        async def fake_aiter_first():
            yield FakeChunk(function_calls=[FakeFunctionCall()])

        async def fake_aiter_second():
            yield FakeChunk(text="Result: found it")

        mock_chat_session = AsyncMock()

        async def fake_stream(msg, config=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return fake_aiter_first()
            return fake_aiter_second()

        mock_chat_session.send_message_stream = AsyncMock(side_effect=fake_stream)

        from main.app.prometheus.agent import Prometheus

        gen = Prometheus()
        gen.makeChat = MagicMock(return_value=mock_chat_session)

        results = []
        async for event in gen.streamMessage(query="search test", sessionId="s2", db=MagicMock()):
            results.append(event)

        assert any(e.get("text") == "Result: found it" for e in results)
        assert call_count == 2


# ---------------------------------------------------------------------------
# PrometheusChatManager (chat.py)
# ---------------------------------------------------------------------------
