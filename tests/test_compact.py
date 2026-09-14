import time
import pytest
from unittest.mock import patch, MagicMock
import main.app.prometheus.compact as compactMod
from main.app.prometheus.compact import (
    extractTickers,
    extractMetrics,
    extractDecisions,
    extractSnapshots,
    extractToolCalls,
    buildSummary,
    countTokens,
    getTokenizer,
    FALLBACK_FIELDS,
    PrometheusCompactor,
    EPISODE_CAP,
    getMetricRegex,
    loadFieldData,
)


def mockDbFactory(first=None):
    """Return a MagicMock db whose query chain resolves first() to `first`."""
    mockDb = MagicMock()
    mockDb.query.return_value.filter.return_value.first.return_value = first
    return mockDb


class TestExtractTickers:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Análise de PETR4", ["PETR4"]),
            ("PETR4 e VALE3 e ITUB4", ["PETR4", "VALE3", "ITUB4"]),
            ("PETR4 e depois PETR4", ["PETR4"]),
            ("O P/L da PETR4 está abaixo de VALE3", ["PETR4", "VALE3"]),
        ],
    )
    def test_ticker_cases(self, text, expected):
        assert extractTickers(text) == expected

    @pytest.mark.parametrize("text", ["nenhum ticker aqui", "HIGH e LOW"])
    def test_no_tickers_found(self, text):
        assert extractTickers(text) == []


class TestExtractMetrics:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("O P/L está em 5.2x", ["P/L"]),
            ("ROE de 15% e DY de 8%", ["ROE", "DY"]),
            ("P/L de 5x", ["P/L"]),
        ],
    )
    def test_metric_cases(self, text, expected):
        result = extractMetrics(text)
        for metric in expected:
            assert metric in result

    def test_cagr_metrics(self):
        oldField, oldRegex = compactMod.fieldData, compactMod.metricRegex
        compactMod.fieldData = None
        compactMod.metricRegex = None
        with patch(
            "main.app.prometheus.compact.loadFieldData",
            return_value={"historical": [], "fundamental": []},
        ):
            result = extractMetrics("INVESTING SCORE de 85 e DY de 12%")
        compactMod.fieldData, compactMod.metricRegex = oldField, oldRegex
        assert "INVESTING SCORE" in result
        assert "DY" in result

    def test_no_metrics(self):
        assert extractMetrics("texto sem métricas") == []


class TestExtractDecisions:
    @pytest.mark.parametrize(
        "content,keyword",
        [
            ("Prefiro ações de dividendos", "dividendos"),
            ("Sempre use P/VP abaixo de 1.0", None),
        ],
    )
    def test_decision_cases(self, content, keyword):
        result = extractDecisions([{"content": content}])
        assert len(result) >= 1
        if keyword is not None:
            assert keyword in result[0].lower()

    def test_no_decisions(self):
        msgs = [{"content": "Qual é o P/L da PETR4?"}]
        assert extractDecisions(msgs) == []

    def test_empty_messages(self):
        assert extractDecisions([]) == []


class TestExtractToolCalls:
    @pytest.mark.parametrize(
        "event,expected",
        [
            (
                {"eventType": "tool_call", "metadata": {"toolName": "get_fundamental", "args": {"search": "PETR4"}}},
                "get_fundamental(PETR4)",
            ),
            (
                {"eventType": "tool_call", "metadata": {"toolName": "list_fields", "args": {}}},
                "list_fields",
            ),
        ],
    )
    def test_tool_cases(self, event, expected):
        assert expected in extractToolCalls([event])

    def test_skips_non_tool_events(self):
        events = [{"eventType": "turn_end", "metadata": {}}]
        assert extractToolCalls(events) == []


class TestBuildSummary:
    def test_all_sections(self):
        result = buildSummary(["PETR4"], ["get_fundamental(PETR4)"], ["Prefiro value"], ["P/L"], ["P/L: 5.2x"])
        assert "PETR4" in result
        assert "get_fundamental" in result
        assert "P/L" in result

    def test_empty(self):
        result = buildSummary([], [], [], [], [])
        assert "no extractable data" in result


class TestCountTokens:
    def test_empty(self):
        assert countTokens("") == 0

    def test_with_tokenizer(self):
        with patch("main.app.prometheus.compact.getTokenizer") as mockGet:
            mockTok = MagicMock()
            mockTok.count_tokens.return_value.total_tokens = 10
            mockGet.return_value = mockTok
            assert countTokens("test text") == 10

    def test_without_tokenizer(self):
        with patch("main.app.prometheus.compact.getTokenizer", return_value=None):
            assert countTokens("1234567890") == 3

    def test_fallback_on_exception(self):
        with patch("main.app.prometheus.compact.getTokenizer") as mockGet:
            mockTok = MagicMock()
            mockTok.count_tokens.side_effect = RuntimeError("broken")
            mockGet.return_value = mockTok
            assert countTokens("12345678") == 2


class TestGetTokenizer:
    def test_caches_instance(self):
        import main.app.prometheus.compact as mod

        mod.tokenizer = None
        with patch("main.app.prometheus.compact.genai") as mockGenai:
            mockGenai.LocalTokenizer.return_value = MagicMock()
            t1 = getTokenizer()
            t2 = getTokenizer()
            assert t1 is t2
            assert mockGenai.LocalTokenizer.call_count == 1
        mod.tokenizer = None

    def test_returns_none_on_failure(self):
        import main.app.prometheus.compact as mod

        mod.tokenizer = None
        with patch("main.app.prometheus.compact.genai") as mockGenai:
            mockGenai.LocalTokenizer.side_effect = RuntimeError("no model")
            assert getTokenizer() is None
        mod.tokenizer = None


class TestPrometheusCompactor:
    def setup_method(self):
        self.compactor = PrometheusCompactor()

    def test_should_compact_below_budget(self):
        history = [{"role": "user", "content": "short"}]
        assert self.compactor.shouldCompact(history) is False

    def test_should_compact_above_budget(self):
        history = [{"role": "user", "content": "x" * 40000}]
        assert self.compactor.shouldCompact(history) is True

    def test_should_compact_empty(self):
        assert self.compactor.shouldCompact([]) is False

    def test_extract_basic(self):
        chunk = [
            {"role": "user", "content": "Analise PETR4 e VALE3"},
            {
                "role": "loop_event",
                "eventType": "tool_call",
                "metadata": {"toolName": "get_fundamental", "args": {"search": "PETR4"}},
            },
            {"role": "loop_event", "eventType": "tool_result", "metadata": {"result": {"P/L": 5.2}}},
        ]
        result = self.compactor.extractEpisode(chunk)
        assert "PETR4" in result["entities"]
        assert "VALE3" in result["entities"]
        assert "get_fundamental(PETR4)" in result["summary"] or "get_fundamental" in result["summary"]

    def test_extract_uses_field_registry(self):
        chunk = [{"role": "user", "content": "P/L de 5x e ROE 15%"}]
        with patch("main.app.prometheus.compact.extractMetrics") as mockExtract:
            mockExtract.return_value = ["P/L", "ROE"]
            result = self.compactor.extractEpisode(chunk)
            mockExtract.assert_called_once_with("P/L de 5x e ROE 15%")

    def test_consolidate_under_cap(self):
        episodes = [{"id": f"ep_{i}", "summary": f"Episode {i}"} for i in range(5)]
        assert len(self.compactor.consolidate(episodes)) == 5

    def test_consolidate_over_cap(self):
        episodes = [{"id": f"ep_{i}", "summary": f"Episode {i}", "keyDecisions": [], "entities": []} for i in range(15)]
        result = self.compactor.consolidate(episodes)
        assert len(result) == 11
        assert result[0]["id"].startswith("ep_")

    def test_consolidate_preserves_decisions(self):
        episodes = [
            {"id": f"ep_{i}", "summary": f"Ep {i}", "keyDecisions": [f"decision {i}"], "entities": []}
            for i in range(15)
        ]
        result = self.compactor.consolidate(episodes)
        merged = result[0]
        assert len(merged["keyDecisions"]) == 5

    def test_get_episodes_empty_session(self):
        assert self.compactor.getEpisodes(mockDbFactory(None), "sid1") == []

    @pytest.mark.parametrize("summary", [None, "{invalid json", '"just a string"'])
    def test_get_episodes_invalid_summary(self, summary):
        session = MagicMock()
        session.summary = summary
        assert self.compactor.getEpisodes(mockDbFactory(session), "sid1") == []

    def test_get_episodes_valid(self):
        session = MagicMock()
        session.summary = '[{"id": "ep_1", "summary": "test"}]'
        result = self.compactor.getEpisodes(mockDbFactory(session), "sid1")
        assert len(result) == 1
        assert result[0]["id"] == "ep_1"

    @pytest.mark.parametrize("episodes", [[], [{"id": "ep_1"}]])
    def test_get_compactable_chunk_no_usable_episodes(self, episodes):
        history = [{"role": "user", "content": "msg1"}]
        assert self.compactor.getCompactableChunk(history, episodes) == history

    def test_get_compactable_chunk_filters_by_timestamp(self):
        history = [
            {"role": "user", "content": "old", "timestamp": "2025-01-01"},
            {"role": "user", "content": "new", "timestamp": "2025-06-01"},
        ]
        episodes = [{"id": "ep_1", "time": "2025-03-01"}]
        result = self.compactor.getCompactableChunk(history, episodes)
        assert len(result) == 1
        assert result[0]["content"] == "new"

    def test_get_compactable_chunk_fallback_last_10(self):
        history = [{"role": "user", "content": f"msg{i}", "timestamp": "2025-01-01"} for i in range(20)]
        episodes = [{"id": "ep_1", "time": "2025-12-01"}]
        result = self.compactor.getCompactableChunk(history, episodes)
        assert len(result) == 10
        assert result[0]["content"] == "msg10"

    def test_compact_returns_none_no_session(self):
        assert self.compactor.compact(mockDbFactory(None), "sid1") is None

    def test_compact_returns_none_no_history(self):
        session = MagicMock()
        session.history = []
        assert self.compactor.compact(mockDbFactory(session), "sid1") is None

    def test_compact_returns_none_below_budget(self):
        session = MagicMock()
        session.history = [{"role": "user", "content": "short"}]
        session.summary = None
        assert self.compactor.compact(mockDbFactory(session), "sid1") is None

    def test_compact_creates_episode_above_budget(self):
        session = MagicMock()
        session.history = [{"role": "user", "content": "x" * 40000}]
        session.summary = None
        mockDb = mockDbFactory(session)
        result = self.compactor.compact(mockDb, "sid1")
        assert result is not None
        assert result["id"].startswith("ep_")
        assert "summary" in result
        mockDb.commit.assert_called_once()


class TestLoadFieldDataRetry:
    def test_retryAfterFailure(self):
        compactMod.fieldData = None
        fakeResponse = MagicMock()
        fakeResponse.json.return_value = {"historical": {"LUCRO LIQUIDO": [2023]}, "fundamental": ["P/L"]}
        mockSession = MagicMock()
        mockSession.get.side_effect = [Exception("boom"), fakeResponse]
        with patch("main.app.prometheus.compact.getSession", return_value=mockSession):
            first = loadFieldData()
            assert first == {"historical": [], "fundamental": []}
            assert compactMod.fieldData is None
            second = loadFieldData()
            assert "LUCRO LIQUIDO" in second["historical"]
            assert second["fundamental"] == ["P/L"]
        compactMod.fieldData = None
