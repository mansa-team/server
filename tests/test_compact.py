import pytest
from unittest.mock import patch, MagicMock
from main.app.prometheus.compact import (
    extractTickers, extractMetrics, extractDecisions,
    extractSnapshots, extractToolCalls, buildSummary, charCount,
    FieldRegistry, FALLBACK_FIELDS,
)


class TestExtractTickers:
    def test_single_ticker(self):
        assert extractTickers("Análise de PETR4") == ["PETR4"]

    def test_multiple_tickers(self):
        result = extractTickers("PETR4 e VALE3 e ITUB4")
        assert result == ["PETR4", "VALE3", "ITUB4"]

    def test_no_tickers(self):
        assert extractTickers("nenhum ticker aqui") == []

    def test_deduplication(self):
        assert extractTickers("PETR4 e depois PETR4") == ["PETR4"]

    def test_does_not_match_4_letter_words(self):
        assert extractTickers("HIGH e LOW") == []

    def test_ticker_in_context(self):
        text = "O P/L da PETR4 está abaixo de VALE3"
        assert extractTickers(text) == ["PETR4", "VALE3"]


class TestExtractMetrics:
    def test_single_metric(self):
        assert "P/L" in extractMetrics("O P/L está em 5.2x")

    def test_multiple_metrics(self):
        result = extractMetrics("ROE de 15% e DY de 8%")
        assert "ROE" in result
        assert "DY" in result

    def test_cagr_metrics(self):
        result = extractMetrics("INVESTING SCORE de 85 e DY de 12%")
        assert "INVESTING SCORE" in result
        assert "DY" in result

    def test_no_metrics(self):
        assert extractMetrics("texto sem métricas") == []

    def test_uses_fallback_when_no_registry(self):
        result = extractMetrics("P/L de 5x")
        assert "P/L" in result


class TestFieldRegistry:
    def test_singleton(self):
        r1 = FieldRegistry()
        r2 = FieldRegistry()
        assert r1 is r2

    def test_fallback_fields_on_api_failure(self):
        registry = FieldRegistry()
        registry.invalidate()
        fields = registry.fetchFields()
        assert "P/L" in fields
        assert "ROE" in fields
        assert len(fields) >= 20

    def test_build_metric_regex(self):
        registry = FieldRegistry()
        registry.fields = ["P/L", "ROE", "DY", "CAGR LUCROS 10 ANOS"]
        regex = registry.buildMetricRegex()
        assert "P/L" in regex.pattern
        assert "ROE" in regex.pattern
        idx_cagr = regex.pattern.find("CAGR LUCROS 10 ANOS")
        idx_pl = regex.pattern.find("P/L")
        assert idx_cagr < idx_pl

    def test_invalidate(self):
        registry = FieldRegistry()
        registry.fields = ["P/L"]
        registry.invalidate()
        assert registry.fields is None


class TestExtractDecisions:
    def test_preference(self):
        msgs = [{"content": "Prefiro ações de dividendos"}]
        result = extractDecisions(msgs)
        assert len(result) >= 1
        assert "dividendos" in result[0].lower()

    def test_always_keyword(self):
        msgs = [{"content": "Sempre use P/VP abaixo de 1.0"}]
        result = extractDecisions(msgs)
        assert len(result) >= 1

    def test_no_decisions(self):
        msgs = [{"content": "Qual é o P/L da PETR4?"}]
        assert extractDecisions(msgs) == []

    def test_empty_messages(self):
        assert extractDecisions([]) == []


class TestExtractToolCalls:
    def test_tool_with_ticker(self):
        events = [{"eventType": "tool_call", "metadata": {"toolName": "get_fundamental", "args": {"search": "PETR4"}}}]
        result = extractToolCalls(events)
        assert "get_fundamental(PETR4)" in result

    def test_tool_without_ticker(self):
        events = [{"eventType": "tool_call", "metadata": {"toolName": "list_fields", "args": {}}}]
        result = extractToolCalls(events)
        assert "list_fields" in result

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


class TestCharCount:
    def test_basic(self):
        assert charCount("1234") == 1
        assert charCount("") == 0


from main.app.prometheus.compact import PrometheusCompactor, EPISODE_CAP


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
            {"role": "loop_event", "eventType": "tool_call", "metadata": {"toolName": "get_fundamental", "args": {"search": "PETR4"}}},
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
            mockExtract.assert_called_once()
            callArgs = mockExtract.call_args
            assert callArgs[1].get("registry") is not None or callArgs[0][1] is not None

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

    def test_has_field_registry(self):
        assert self.compactor.registry is not None
        assert isinstance(self.compactor.registry, FieldRegistry)
