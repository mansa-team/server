"""Tests for PrometheusSummarizer: R5 (smart truncation), summarization trigger, edge cases."""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from main.app.prometheus.summarizer import PrometheusSummarizer, smartTruncate
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
    @patch("main.app.prometheus.summarizer.genai.Client")
    def test_each_summarize_creates_new_episode(self, mock_genai, db_session, fake_session_with_45_messages):
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
        # After first summarize: history untouched at 50
        # Simulate new messages growing to 100 (next % 50 boundary)
        fake_session_with_45_messages.history = [
            {"role": "user", "content": f"Msg {i}", "timestamp": datetime.now().isoformat()} for i in range(100)
        ]
        db_session.commit()
        ep2 = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)

        assert ep1 is not None
        assert ep2 is not None
        assert ep1["id"] != ep2["id"]  # different episodes
        episodes = summarizer.getEpisodes(db_session, fake_session_with_45_messages.sessionId)
        assert len(episodes) == 2


# ── R1: Summarize Trims History ───────────────────────────────────────


class TestSummarizeTrimsHistory:
    @patch("main.app.prometheus.summarizer.genai.Client")
    def test_summarize_does_not_trim_history(self, mock_genai, db_session, fake_session_with_45_messages):
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
        """Storing more than20 episodes should keep only the last20."""
        summarizer = PrometheusSummarizer()
        # Pre-populate21 episodes directly in the summary
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

        # Now summarize — should append episode22, then cap to last20
        mock_resp = MagicMock()
        mock_resp.parsed = {"summary": "New episode", "keyDecisions": [], "entities": []}
        with patch("main.app.prometheus.summarizer.genai.Client") as mock_genai:
            mock_genai.return_value.models.generate_content.return_value = mock_resp
            summarizer.summarize(db_session, "test-cap")

        result = summarizer.getEpisodes(db_session, "test-cap")
        assert len(result) == 20
        # First episode should be ep_0002 (0 and1 dropped)
        assert result[0]["id"] == "ep_0002"


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
