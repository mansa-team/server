import asyncio
import json

import main.controller.prometheus_controller as controller_mod
import pytest
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


def test_forward_terminates_when_finished_channel_has_empty_replay(monkeypatch):
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

    lines = asyncio.run(scenario())
    data = [ln for ln in lines if ln.startswith("data: ")]
    done_events = [json.loads(ln[6:].strip()) for ln in data if ln[6:].strip() != "[DONE]"]
    assert {"type": "done"} in done_events
    assert "data: [DONE]\n\n" in data
