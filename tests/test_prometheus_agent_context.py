"""Tests for Prometheus agent context: R2 (bounded episode injection)."""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from main.app.prometheus.agent import Prometheus
from main.app.prometheus.state import HarnessState
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
            state=HarnessState(),
            sessionId=fake_session_with_120_messages.sessionId,
        )
        episode_count = prompt.count("[Episode")
        assert episode_count <= 5
        assert episode_count >= 1

    def test_episode_format_is_single_line(self, dbSession, fake_session_with_120_messages):
        prompt = Prometheus.buildSystemPrompt(
            userId=1,
            db=dbSession,
            state=HarnessState(),
            sessionId=fake_session_with_120_messages.sessionId,
        )
        lines = prompt.split("\n")
        episode_lines = [ln for ln in lines if ln.startswith("[Episode")]
        for line in episode_lines:
            assert "|" in line  # compressed single-line format

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
            state=HarnessState(),
            sessionId="test-empty",
        )
        assert "[Episode" not in prompt
