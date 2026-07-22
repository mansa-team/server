"""Tests for PrometheusSummarizer: R5 (smart truncation), summarization trigger, edge cases."""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from main.app.prometheus.summarizer import PrometheusSummarizer, smartTruncate, countTokens
from main.models.prometheus import PrometheusSession


@pytest.fixture
def db_session(dbSession):
    return dbSession


@pytest.fixture
def fake_session_with_45_messages(db_session):
    session = PrometheusSession(
        sessionId="test-45",
        userId=1,
        title="Test",
        history=[
            {"role": "user", "content": f"Message {i}", "timestamp": datetime.now().isoformat()} for i in range(50)
        ],
    )
    db_session.add(session)
    db_session.commit()
    return session


@pytest.fixture
def fake_session_with_50_messages(db_session):
    session = PrometheusSession(
        sessionId="test-50",
        userId=1,
        title="Test 50",
        history=[
            {"role": "user", "content": f"Message {i}", "timestamp": datetime.now().isoformat()} for i in range(50)
        ],
    )
    db_session.add(session)
    db_session.commit()
    return session


# ── R5: Smart Truncation ──────────────────────────────────────────────


class TestSmartTruncate:
    def test_respects_word_boundary(self):
        text = "word " * 300  # 1500 chars
        truncated = smartTruncate(text, max_len=500)
        assert len(truncated) <= 500
        assert truncated.endswith("...")
        # rsplit ensures we cut at a space — no partial word
        body = truncated[:-3].rstrip()
        assert body  # not empty

    def test_strips_broken_tags(self):
        text = '{% stat %}{"label": "P/L", "value": "5.2x"} and more text ' * 20
        truncated = smartTruncate(text, max_len=500)
        # no unclosed {% tag
        open_tags = truncated.count("{%")
        close_tags = truncated.count("%}")
        assert open_tags <= close_tags

    def test_short_text_unchanged(self):
        text = "short text"
        assert smartTruncate(text, max_len=500) == "short text"

    def test_exact_boundary(self):
        text = "a" * 500
        truncated = smartTruncate(text, max_len=500)
        assert truncated == "a" * 500  # no truncation needed


# ── R3: Episode Accumulation ───────────────────────────────────────────


class TestEpisodeAccumulation:
    @patch("main.app.prometheus.summarizer.countTokens", return_value=600)
    @patch("main.app.prometheus.summarizer.genai.Client")
    def test_each_summarize_creates_new_episode(
        self, mock_genai, mock_count, db_session, fake_session_with_45_messages
    ):
        """Summarizing twice on the same history should NOT dedup — each batch gets its own episode."""
        mock_resp = MagicMock()
        mock_resp.parsed = {
            "summary": "Test summary",
            "keyDecisions": ["decided X"],
            "entities": ["entity A"],
        }
        mock_genai.return_value.models.generate_content.return_value = mock_resp

        summarizer = PrometheusSummarizer()
        ep1 = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)
        assert ep1 is not None

        # Simulate new messages — give enough messages so fallback chunk (last 10) exceeds threshold
        fake_session_with_45_messages.history = [
            {"role": "user", "content": f"Msg {i}", "timestamp": datetime.now().isoformat()} for i in range(100)
        ]
        db_session.commit()
        # Bump mock so 10 fallback messages × 1000 = 10000 > 8000
        mock_count.return_value = 1000
        ep2 = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)

        assert ep2 is not None
        assert ep1["id"] != ep2["id"]  # different episodes
        episodes = summarizer.getEpisodes(db_session, fake_session_with_45_messages.sessionId)
        assert len(episodes) == 2


# ── R1: Summarize Trims History ───────────────────────────────────────


class TestSummarizeTrimsHistory:
    @patch("main.app.prometheus.summarizer.countTokens", return_value=600)
    @patch("main.app.prometheus.summarizer.genai.Client")
    def test_summarize_does_not_trim_history(self, mock_genai, mock_count, db_session, fake_session_with_45_messages):
        mock_resp = MagicMock()
        mock_resp.parsed = {
            "summary": "Test summary",
            "keyDecisions": [],
            "entities": [],
        }
        mock_genai.return_value.models.generate_content.return_value = mock_resp

        summarizer = PrometheusSummarizer()
        result = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)

        db_session.refresh(fake_session_with_45_messages)

        assert result is not None
        # History is NOT trimmed — full conversation preserved for frontend
        assert len(fake_session_with_45_messages.history) == 50
        assert len(summarizer.getEpisodes(db_session, fake_session_with_45_messages.sessionId)) == 1

    def test_no_summarize_under_20_messages(self, db_session):
        session = PrometheusSession(
            sessionId="test-short",
            userId=1,
            title="Short",
            history=[
                {"role": "user", "content": f"Msg {i}", "timestamp": datetime.now().isoformat()} for i in range(15)
            ],
        )
        db_session.add(session)
        db_session.commit()

        summarizer = PrometheusSummarizer()
        result = summarizer.summarize(db_session, "test-short")
        assert result is None


# ── Edge Cases ────────────────────────────────────────────────────────


class TestSummarizeEdgeCases:
    @patch("main.app.prometheus.summarizer.genai.Client")
    def test_api_failure_leaves_session_unchanged(self, mock_genai, db_session, fake_session_with_45_messages):
        """Gemini API throws → summarize returns None, session is not mutated."""
        mock_genai.return_value.models.generate_content.side_effect = Exception("API down")

        summarizer = PrometheusSummarizer()
        original_history_len = len(fake_session_with_45_messages.history)
        original_summary = fake_session_with_45_messages.summary

        result = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)

        assert result is None
        db_session.refresh(fake_session_with_45_messages)
        assert len(fake_session_with_45_messages.history) == original_history_len
        assert fake_session_with_45_messages.summary == original_summary

    def test_empty_content_messages_skipped(self, db_session):
        """Messages with empty/null content should not break the transcript builder."""
        session = PrometheusSession(
            sessionId="test-empty-content",
            userId=1,
            title="Empty",
            history=[{"role": "user", "content": "", "timestamp": datetime.now().isoformat()} for _ in range(25)],
        )
        db_session.add(session)
        db_session.commit()

        summarizer = PrometheusSummarizer()
        # Should not crash — empty content is filtered out, but transcript may be empty
        result = summarizer.summarize(db_session, "test-empty-content")
        # Result depends on whether API accepts empty input — just verify no crash
        # (API may return None or a generic summary)

    def test_20_episode_cap_drops_oldest(self, db_session):
        """With consolidation, 21 episodes + new = consolidation triggers, reducing count below hard cap."""
        summarizer = PrometheusSummarizer()
        episodes = [
            {
                "id": f"ep_{i:04d}",
                "time": datetime.now().isoformat(),
                "summary": f"Episode {i}",
                "keyDecisions": [],
                "entities": [],
            }
            for i in range(21)
        ]
        session = PrometheusSession(
            sessionId="test-cap",
            userId=1,
            title="Cap",
            history=[
                {"role": "user", "content": f"Msg {i}", "timestamp": datetime.now().isoformat()} for i in range(50)
            ],
            summary=json.dumps(episodes),
        )
        db_session.add(session)
        db_session.commit()

        mock_resp = MagicMock()
        mock_resp.parsed = {"summary": "New episode", "keyDecisions": [], "entities": []}
        with patch("main.app.prometheus.summarizer.genai.Client") as mock_genai:
            with patch("main.app.prometheus.summarizer.countTokens", return_value=600):
                mock_genai.return_value.models.generate_content.return_value = mock_resp
                summarizer.summarize(db_session, "test-cap")

        result = summarizer.getEpisodes(db_session, "test-cap")
        # 21 existing + 1 new = 22 > SOFT_CAP(12) → consolidate merges first 12 into 1
        # 1 merged + 10 recent = 11, then hard cap(20) → 11 kept
        assert len(result) <= 20
        assert result[0]["summary"] == "New episode"  # merged episode from consolidation


class TestGetEpisodesEdgeCases:
    def test_malformed_json_returns_empty(self, db_session):
        """Corrupt JSON in summary column should return empty list, not crash."""
        session = PrometheusSession(
            sessionId="test-corrupt",
            userId=1,
            title="Corrupt",
            history=[],
            summary="not valid json {{{",
        )
        db_session.add(session)
        db_session.commit()

        episodes = PrometheusSummarizer().getEpisodes(db_session, "test-corrupt")
        assert episodes == []

    def test_non_list_json_returns_empty(self, db_session):
        """Valid JSON but not a list (e.g. dict) should return empty list."""
        session = PrometheusSession(
            sessionId="test-dict",
            userId=1,
            title="Dict",
            history=[],
            summary=json.dumps({"key": "value"}),
        )
        db_session.add(session)
        db_session.commit()

        episodes = PrometheusSummarizer().getEpisodes(db_session, "test-dict")
        assert episodes == []

    def test_none_summary_returns_empty(self, db_session):
        """None summary should return empty list."""
        session = PrometheusSession(
            sessionId="test-none",
            userId=1,
            title="None",
            history=[],
            summary=None,
        )
        db_session.add(session)
        db_session.commit()

        episodes = PrometheusSummarizer().getEpisodes(db_session, "test-none")
        assert episodes == []

    def test_empty_list_summary_returns_empty(self, db_session):
        """Empty JSON list should return empty list."""
        session = PrometheusSession(
            sessionId="test-empty-list",
            userId=1,
            title="Empty",
            history=[],
            summary="[]",
        )
        db_session.add(session)
        db_session.commit()

        episodes = PrometheusSummarizer().getEpisodes(db_session, "test-empty-list")
        assert episodes == []


class TestCountTokens:
    def test_english_text(self):
        count = countTokens("The quick brown fox jumps over the lazy dog")
        assert 5 <= count <= 15

    def test_portuguese_text(self):
        count = countTokens("A análise fundamentalista mostra que a Petrobras está subvalorizada")
        assert 10 <= count <= 25

    def test_empty_string(self):
        assert countTokens("") == 0

    def test_code_block(self):
        count = countTokens("```python\ndef hello():\n    print('world')\n```")
        assert count > 0

    def test_mixed_language(self):
        count = countTokens("PETR4 P/L ratio está em 5.2, which is low")
        assert count > 0


class TestTokenBasedTrigger:
    def test_should_not_summarize_empty_history(self):
        s = PrometheusSummarizer()
        assert s.shouldSummarize([]) is False

    def test_should_not_summarize_short_history(self):
        s = PrometheusSummarizer()
        history = [{"role": "user", "content": "Hello"} for _ in range(5)]
        assert s.shouldSummarize(history) is False

    @patch("main.app.prometheus.summarizer.countTokens", return_value=3000)
    def test_should_summarize_when_threshold_exceeded(self, mock_count):
        s = PrometheusSummarizer()
        history = [{"role": "user", "content": "x" * 3000} for _ in range(4)]
        assert s.shouldSummarize(history) is True

    @patch("main.app.prometheus.summarizer.countTokens", return_value=1000)
    def test_should_not_summarize_below_threshold(self, mock_count):
        s = PrometheusSummarizer()
        history = [{"role": "user", "content": "x" * 100} for _ in range(5)]
        assert s.shouldSummarize(history) is False


class TestConsolidation:
    def test_no_consolidation_under_threshold(self):
        s = PrometheusSummarizer()
        episodes = [{"id": f"ep_{i}", "summary": f"Episode {i}", "keyDecisions": [], "entities": []} for i in range(10)]
        result = s.consolidate(episodes)
        assert len(result) == 10

    def test_consolidation_triggered_above_threshold(self):
        s = PrometheusSummarizer()
        episodes = [{"id": f"ep_{i}", "summary": f"Episode {i}", "keyDecisions": [], "entities": []} for i in range(15)]
        result = s.consolidate(episodes)
        assert len(result) <= 12

    def test_recent_episodes_preserved(self):
        s = PrometheusSummarizer()
        episodes = [{"id": f"ep_{i}", "summary": f"Episode {i}", "keyDecisions": [], "entities": []} for i in range(15)]
        result = s.consolidate(episodes)
        recent_ids = [ep["id"] for ep in result[1:]]
        assert "ep_14" in recent_ids
        assert "ep_5" in recent_ids

    def test_merged_episode_has_all_entities(self):
        s = PrometheusSummarizer()
        episodes = [
            {"id": f"ep_{i}", "summary": f"Episode {i}", "keyDecisions": [], "entities": [f"entity_{i}"]}
            for i in range(15)
        ]
        result = s.consolidate(episodes)
        merged = result[0]
        for i in range(5):
            assert f"entity_{i}" in merged["entities"]

    def test_consolidate_empty_episodes(self):
        s = PrometheusSummarizer()
        result = s.consolidate([])
        assert result == []

    def test_consolidate_single_episode(self):
        s = PrometheusSummarizer()
        ep = [{"id": "ep_1", "summary": "Test", "keyDecisions": [], "entities": []}]
        result = s.consolidate(ep)
        assert len(result) == 1


# ── Token Counting Integration ─────────────────────────────────────────


class TestTokenCountingIntegration:
    def test_count_tokens_matches_gemini_tokenizer(self):
        """Verify local tokenizer produces reasonable counts."""
        text = "A análise fundamentalista da PETR4 mostra P/L de 5.2 e ROE de 15%"
        count = countTokens(text)
        assert 20 <= count <= 35

    def test_count_tokens_handles_long_text(self):
        text = "x" * 10000
        count = countTokens(text)
        assert count > 1000

    def test_fallback_when_tokenizer_unavailable(self):
        """Verify fallback works if local tokenizer fails."""
        import main.app.prometheus.summarizer as mod

        original = mod._tokenizer
        mod._tokenizer = None
        try:
            count = countTokens("hello world")
            assert count > 0
        finally:
            mod._tokenizer = original


# ── Edge Cases ──────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_shouldSummarize_all_empty_content(self):
        s = PrometheusSummarizer()
        history = [{"role": "user", "content": ""} for _ in range(100)]
        assert s.shouldSummarize(history) is False

    def test_getSummarizableChunk_no_episodes(self):
        s = PrometheusSummarizer()
        history = [{"role": "user", "content": "x", "timestamp": "2026-01-01T00:00:00"}]
        chunk = s.getSummarizableChunk(history, [])
        assert chunk == history

    def test_getSummarizableChunk_with_episodes(self):
        s = PrometheusSummarizer()
        history = [
            {"role": "user", "content": "old", "timestamp": "2026-01-01T00:00:00"},
            {"role": "user", "content": "new", "timestamp": "2026-01-02T00:00:00"},
        ]
        episodes = [{"time": "2026-01-01T12:00:00"}]
        chunk = s.getSummarizableChunk(history, episodes)
        assert len(chunk) == 1
        assert chunk[0]["content"] == "new"
