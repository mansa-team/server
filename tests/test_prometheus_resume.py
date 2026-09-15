import asyncio
import json

import main.controller.prometheus_controller as controller_mod
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import getSession
from main.app.prometheus.agent import Prometheus
from main.app.prometheus.stream_bus import streamBus
from main.models.base import Base


class FakePrometheus(Prometheus):
    async def streamMessage(self, query=None, sessionId=None, db=None, user=None, file=None):
        yield {"type": "text", "text": "first"}
        yield {"type": "text", "text": " second"}


@pytest.fixture(autouse=True)
def isolate_bus():
    streamBus.channels.clear()
    yield
    streamBus.channels.clear()


@pytest.fixture(autouse=True)
def no_gemini_client(monkeypatch):
    """chat_stream builds Prometheus() per run; __init__ creates a genai.Client
    which requires a real Gemini API key that CI doesn't have. These tests mock
    streamMessage, so the constructor is a no-op."""
    monkeypatch.setattr(Prometheus, "__init__", lambda self: None)


@pytest.fixture(autouse=True)
def sqlite_db(client, monkeypatch):
    """Route the prometheus router + background runner to in-memory sqlite so
    these tests don't need a live MySQL server (docker 'db' host)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    client.app.dependency_overrides[getSession] = lambda: session_factory()
    # The runner in prometheus_controller creates its own SessionLocal() from
    # config; patch it so the background run also uses sqlite.
    monkeypatch.setattr(controller_mod, "SessionLocal", session_factory)

    yield

    client.app.dependency_overrides.pop(getSession, None)
    engine.dispose()


def payloads(resp):
    lines = [line for line in resp.iter_lines() if line.startswith("data: ")]
    return [json.loads(line[6:]) for line in lines if line[6:] != "[DONE]"]


def test_post_stream_then_resume_replays_from_cursor(client, monkeypatch):
    monkeypatch.setattr(Prometheus, "streamMessage", FakePrometheus.streamMessage)

    with client.stream("POST", "/prometheus/chat/stream", data={"query": "oi"}, files={}) as r:
        assert r.status_code == 200
        result_payloads = payloads(r)

    types = [p["type"] for p in result_payloads]
    assert types[0] == "session"
    assert types[-1] == "done"
    assert [p["text"] for p in result_payloads if p["type"] == "text"] == ["first", " second"]
    sid = result_payloads[0]["sessionId"]

    # Resume with cursor=2: "first" was consumed, replay must start at " second"
    with client.stream("GET", f"/prometheus/chat/stream/{sid}?cursor=2") as r2:
        assert r2.status_code == 200
        payloads2 = payloads(r2)

    assert [p["text"] for p in payloads2 if p["type"] == "text"] == [" second"]
    assert payloads2[-1]["type"] == "done"


def test_resume_unknown_session_is_forbidden(client):
    with client.stream("GET", "/prometheus/chat/stream/nope?cursor=0") as r:
        assert r.status_code == 403


def test_resume_requires_valid_cursor(client, monkeypatch):
    monkeypatch.setattr(Prometheus, "streamMessage", FakePrometheus.streamMessage)
    with client.stream("POST", "/prometheus/chat/stream", data={"query": "oi"}, files={}) as r:
        sid = payloads(r)[0]["sessionId"]

    with client.stream("GET", f"/prometheus/chat/stream/{sid}?cursor=-1") as r2:
        assert r2.status_code == 422


def test_second_post_to_same_session_replaces_log(client, monkeypatch):
    """Regression (C1): a second POST to the SAME session must stream only the
    second run's events; the stale log of the finished first run must not be
    replayed (which would terminate the stream at the stale done)."""
    monkeypatch.setattr(Prometheus, "streamMessage", FakePrometheus.streamMessage)

    with client.stream("POST", "/prometheus/chat/stream", data={"query": "oi"}, files={}) as r:
        assert r.status_code == 200
        first = payloads(r)
    sid = first[0]["sessionId"]

    with client.stream("POST", "/prometheus/chat/stream", data={"query": "oi", "sessionId": sid}, files={}) as r2:
        assert r2.status_code == 200
        second = payloads(r2)

    types = [p["type"] for p in second]
    assert types == ["session", "text", "text", "done"]
    assert [p["text"] for p in second if p["type"] == "text"] == ["first", " second"]


async def test_forward_terminates_when_finished_channel_has_empty_replay(monkeypatch):
    """Regression (I2): resuming a finished channel at cursor == len(events)
    yields an empty replay, so forward must terminate via the finished check
    instead of streaming keepalives forever. No DB needed - drives
    streamBus.forward directly against a prepared StreamBus."""
    real_wait_for = asyncio.wait_for

    async def quick_wait_for(coro, timeout=None):
        return await real_wait_for(coro, timeout=0.05)

    monkeypatch.setattr(asyncio, "wait_for", quick_wait_for)

    async def scenario():
        async def runner():
            yield {"type": "text", "text": "x"}

        # Drive the module-level singleton directly: _forward subscribes via
        # streamBus, so a local StreamBus() instance would never be visible to it.
        streamBus.startRun("s1", runner)
        q0, ch = streamBus.subscribe("s1")
        assert (await asyncio.wait_for(q0.get(), 1))["text"] == "x"
        assert await asyncio.wait_for(q0.get(), 1) == {"type": "done"}
        streamBus.unsubscribe("s1", q0)
        assert ch.finished is True

        # events = [text, done]; cursor=2 replays nothing.
        return [line async for line in streamBus.forward("s1", cursor=2)]

    lines = await scenario()
    data = [ln for ln in lines if ln.startswith("data: ")]
    done_events = [json.loads(ln[6:].strip()) for ln in data if ln[6:].strip() != "[DONE]"]
    assert {"type": "done"} in done_events
    assert "data: [DONE]\n\n" in data


# ---- moved from test_prometheus_auth_coverage.py (TestPrometheusChatManager) ----


class TestPrometheusChatManager:
    """Cover all methods in chat.py (lines 11-120)."""

    def test_init(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mgr = PrometheusChatManager()
        assert mgr is not None

    def test_get_user_sessions(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()

        mock_session1 = MagicMock()
        mock_session1.sessionId = "s1"
        mock_session1.title = "Title 1"
        mock_session1.lastActivity = datetime(2026, 3, 23, 12, 0, 0)

        mock_session2 = MagicMock()
        mock_session2.sessionId = "s2"
        mock_session2.title = "Title 2"
        mock_session2.lastActivity = None

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_session1,
            mock_session2,
        ]

        result = PrometheusChatManager.getUserSessions(mock_db, userId=1)
        assert len(result) == 2
        assert result[0]["sessionId"] == "s1"
        assert result[0]["lastActivity"] == "2026-03-23T12:00:00"
        assert result[1]["lastActivity"] is None

    def test_create_session(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()

        result = PrometheusChatManager.createSession(mock_db, userId=1, title="Test")
        assert isinstance(result, str)
        assert len(result) > 0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_update_session_title_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.updateSessionTitle(mock_db, "sess-123", "New Title")
        assert result is True
        assert mock_session.title == "New Title"
        mock_db.commit.assert_called_once()

    def test_update_session_title_not_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.updateSessionTitle(mock_db, "nonexistent", "Title")
        assert result is False

    def test_save_message_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = []
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        PrometheusChatManager.appendHistory(
            mock_db, "sess-123", {"role": "user", "content": "Hello", "metadata": {"key": "val"}}
        )

        assert len(mock_session.history) == 1
        assert mock_session.history[0]["role"] == "user"
        assert mock_session.history[0]["content"] == "Hello"
        assert mock_session.history[0]["metadata"] == {"key": "val"}
        mock_db.commit.assert_called_once()

    def test_save_message_history_none(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        PrometheusChatManager.appendHistory(mock_db, "sess-123", {"role": "assistant", "content": "Reply"})

        assert mock_session.history == [
            {
                "role": "assistant",
                "content": "Reply",
                "timestamp": mock_session.history[0]["timestamp"],
            }
        ]

    def test_save_message_not_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        PrometheusChatManager.appendHistory(mock_db, "nonexistent", {"role": "user", "content": "Hello"})

    def test_get_history_with_messages(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = [
            {"role": "user", "content": "Hello", "timestamp": "2026-03-23T12:00:00"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2026-03-23T12:01:00"},
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.getHistory(mock_db, "sess-123")
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["parts"][0]["text"] == "Hello"
        assert result[1]["role"] == "model"

    def test_get_history_empty(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.getHistory(mock_db, "nonexistent")
        assert result == []

    def test_get_history_no_history(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.getHistory(mock_db, "sess-123")
        assert result == []

    def test_get_history_with_limit(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = [{"role": "user", "content": f"msg{i}"} for i in range(30)]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.getHistory(mock_db, "sess-123", limit=5)
        assert len(result) == 5

    def test_delete_session_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.deleteSession(mock_db, "sess-123", userId=1)
        assert result is True
        mock_db.delete.assert_called_once_with(mock_session)
        mock_db.commit.assert_called_once()

    def test_delete_session_not_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.deleteSession(mock_db, "nonexistent", userId=1)
        assert result is False

    def test_verify_session_ownership_true(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = "sess-123"

        result = PrometheusChatManager.verifySessionOwnership(mock_db, "sess-123", userId=1)
        assert result is True

    def test_verify_session_ownership_false(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.verifySessionOwnership(mock_db, "nonexistent", userId=1)
        assert result is False


# ---------------------------------------------------------------------------
# AuthenticationManager (authentication.py)
# ---------------------------------------------------------------------------
