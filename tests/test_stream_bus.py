import asyncio

from main.app.prometheus.stream_bus import StreamBus


def test_subscribe_replays_buffered_events_from_cursor():
    async def scenario():
        bus = StreamBus()
        bus.publish("s1", {"type": "text", "text": "a"})
        bus.publish("s1", {"type": "text", "text": "b"})
        sub = bus.subscribe("s1", cursor=1)
        assert sub is not None
        q, _ch = sub
        assert await asyncio.wait_for(q.get(), 1) == {"type": "text", "text": "b"}
        bus.unsubscribe("s1", q)

    asyncio.run(scenario())


def test_subscribe_unknown_session_returns_none():
    assert StreamBus().subscribe("nope") is None


def test_live_delivery_then_done():
    async def scenario():
        bus = StreamBus()

        async def runner():
            yield {"type": "text", "text": "x"}
            yield {"type": "text", "text": "y"}

        bus.startRun("s1", runner)
        q, ch = bus.subscribe("s1")
        assert await asyncio.wait_for(q.get(), 1) == {"type": "text", "text": "x"}
        assert await asyncio.wait_for(q.get(), 1) == {"type": "text", "text": "y"}
        assert await asyncio.wait_for(q.get(), 1) == {"type": "done"}
        assert ch.finished is True
        bus.unsubscribe("s1", q)

    asyncio.run(scenario())


def test_runner_exception_still_publishes_done():
    async def scenario():
        bus = StreamBus()

        async def runner():
            yield {"type": "text", "text": "boom"}
            raise RuntimeError("boom")

        bus.startRun("s1", runner)
        q, ch = bus.subscribe("s1")
        assert await asyncio.wait_for(q.get(), 1) == {"type": "text", "text": "boom"}
        assert await asyncio.wait_for(q.get(), 1) == {"type": "done"}
        assert ch.finished is True
        bus.unsubscribe("s1", q)

    asyncio.run(scenario())


def test_start_run_replaces_active_run():
    async def scenario():
        bus = StreamBus()

        async def runner1():
            yield {"type": "text", "text": "old"}
            await asyncio.sleep(10)

        async def runner2():
            yield {"type": "text", "text": "new"}

        bus.startRun("s1", runner1)
        q1, _ = bus.subscribe("s1")
        assert (await asyncio.wait_for(q1.get(), 1))["text"] == "old"
        bus.startRun("s1", runner2)
        q2, _ = bus.subscribe("s1")
        assert (await asyncio.wait_for(q2.get(), 1))["text"] == "new"
        assert await asyncio.wait_for(q2.get(), 1) == {"type": "done"}
        bus.unsubscribe("s1", q1)
        bus.unsubscribe("s1", q2)

    asyncio.run(scenario())


def test_second_run_after_finished_run_replaces_log():
    """Regression: a second run on a session whose previous run FINISHED must
    reset the log, not append stale events after the old done."""

    async def scenario():
        bus = StreamBus()

        async def runner1():
            yield {"type": "text", "text": "stale-a"}
            yield {"type": "text", "text": "stale-b"}

        async def runner2():
            yield {"type": "text", "text": "fresh"}

        bus.startRun("s1", runner1)
        q1, ch = bus.subscribe("s1")
        assert (await asyncio.wait_for(q1.get(), 1))["text"] == "stale-a"
        assert (await asyncio.wait_for(q1.get(), 1))["text"] == "stale-b"
        assert await asyncio.wait_for(q1.get(), 1) == {"type": "done"}
        assert ch.finished is True
        bus.unsubscribe("s1", q1)
        await asyncio.sleep(0)  # let the finished task fully finalize

        bus.startRun("s1", runner2)
        q2, ch2 = bus.subscribe("s1")
        assert (await asyncio.wait_for(q2.get(), 1))["text"] == "fresh"
        assert await asyncio.wait_for(q2.get(), 1) == {"type": "done"}
        assert ch2.finished is True
        # Log holds ONLY the second run's events, ending with done.
        assert [e["type"] for e in ch2.events] == ["text", "done"]
        assert [e["text"] for e in ch2.events if e["type"] == "text"] == ["fresh"]
        bus.unsubscribe("s1", q2)

    asyncio.run(scenario())


def test_late_subscriber_cursor_at_last_event_receives_done():
    """A subscriber joining a FINISHED channel with cursor at the last event
    (the done) must get that done as its first queue item."""

    async def scenario():
        bus = StreamBus()

        async def runner():
            yield {"type": "text", "text": "x"}

        bus.startRun("s1", runner)
        q0, ch = bus.subscribe("s1")
        assert (await asyncio.wait_for(q0.get(), 1))["text"] == "x"
        assert await asyncio.wait_for(q0.get(), 1) == {"type": "done"}
        assert ch.finished is True
        bus.unsubscribe("s1", q0)

        # Log is [text, done]; cursor=1 points at the last event.
        q, _ch = bus.subscribe("s1", cursor=1)
        assert await asyncio.wait_for(q.get(), 1) == {"type": "done"}
        bus.unsubscribe("s1", q)

    asyncio.run(scenario())
