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


# ── R3: Deduplication ─────────────────────────────────────────────────


class TestDeduplication:
    @patch("main.app.prometheus.summarizer.genai.Client")
    def test_no_duplicate_episodes(self, mock_genai, db_session, fake_session_with_45_messages):
        mock_resp = MagicMock()
        mock_resp.parsed = {
            "summary": "Test summary",
            "keyDecisions": ["decided X"],
            "entities": ["entity A"],
        }
        mock_genai.return_value.models.generate_content.return_value = mock_resp

        summarizer = PrometheusSummarizer()
        ep1 = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)
        ep2 = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)

        # second call should return same episode (deduped)
        assert ep1 is not None
        assert ep2 is not None
        assert ep1["id"] == ep2["id"]
        episodes = summarizer.getEpisodes(db_session, fake_session_with_45_messages.sessionId)
        assert len(episodes) == 1

    @patch("main.app.prometheus.summarizer.genai.Client")
    def test_different_ranges_create_different_episodes(self, mock_genai, db_session, fake_session_with_45_messages):
        mock_resp = MagicMock()
        mock_resp.parsed = {
            "summary": "Test summary",
            "keyDecisions": [],
            "entities": [],
        }
        mock_genai.return_value.models.generate_content.return_value = mock_resp

        summarizer = PrometheusSummarizer()
        ep1 = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)

        # simulate new messages arriving by extending history
        fake_session_with_45_messages.history = [
            {"role": "user", "content": f"New message {i}", "timestamp": datetime.now().isoformat()} for i in range(100)
        ]
        db_session.commit()

        ep2 = summarizer.summarize(db_session, fake_session_with_45_messages.sessionId)
        # different message range → different episode
        assert ep1 is not None
        assert ep2 is not None
        assert ep1["id"] != ep2["id"]


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
