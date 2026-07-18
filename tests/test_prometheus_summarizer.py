"""Tests for PrometheusSummarizer: R3 (dedup), R5 (smart truncation), R1 (trim)."""

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
            {"role": "user", "content": f"Message {i}", "timestamp": datetime.now().isoformat()} for i in range(45)
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
        # After first summarize: history trimmed to 20
        # Simulate new messages growing back to 50
        fake_session_with_45_messages.history = [
            {"role": "user", "content": f"Msg {i}", "timestamp": datetime.now().isoformat()}
            for i in range(50)
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
    def test_summarize_trims_history_to_20(self, mock_genai, db_session, fake_session_with_45_messages):
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
        assert len(fake_session_with_45_messages.history) == 20
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
