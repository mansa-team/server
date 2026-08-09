import json

import pytest

from main.app.prometheus.agent import Prometheus
from main.app.prometheus.stream_bus import streamBus


class FakePrometheus(Prometheus):
    async def streamMessage(self, query=None, sessionId=None, db=None, user=None):
        yield {"type": "text", "text": "first"}
        yield {"type": "text", "text": " second"}


@pytest.fixture(autouse=True)
def _isolate_bus():
    streamBus._channels.clear()
    yield
    streamBus._channels.clear()


def _payloads(resp):
    lines = [line for line in resp.iter_lines() if line.startswith("data: ")]
    return [json.loads(line[6:]) for line in lines if line[6:] != "[DONE]"]


def test_post_stream_then_resume_replays_from_cursor(client, monkeypatch):
    monkeypatch.setattr(Prometheus, "streamMessage", FakePrometheus.streamMessage)

    with client.stream("POST", "/prometheus/chat/stream", json={"query": "oi"}) as r:
        assert r.status_code == 200
        payloads = _payloads(r)

    types = [p["type"] for p in payloads]
    assert types[0] == "session"
    assert types[-1] == "done"
    assert [p["text"] for p in payloads if p["type"] == "text"] == ["first", " second"]
    sid = payloads[0]["sessionId"]

    # Resume with cursor=2: "first" was consumed, replay must start at " second"
    with client.stream("GET", f"/prometheus/chat/stream/{sid}?cursor=2") as r2:
        assert r2.status_code == 200
        payloads2 = _payloads(r2)

    assert [p["text"] for p in payloads2 if p["type"] == "text"] == [" second"]
    assert payloads2[-1]["type"] == "done"


def test_resume_unknown_session_is_forbidden(client):
    with client.stream("GET", "/prometheus/chat/stream/nope?cursor=0") as r:
        assert r.status_code == 403


def test_resume_requires_valid_cursor(client, monkeypatch):
    monkeypatch.setattr(Prometheus, "streamMessage", FakePrometheus.streamMessage)
    with client.stream("POST", "/prometheus/chat/stream", json={"query": "oi"}) as r:
        sid = _payloads(r)[0]["sessionId"]

    with client.stream("GET", f"/prometheus/chat/stream/{sid}?cursor=-1") as r2:
        assert r2.status_code == 422
