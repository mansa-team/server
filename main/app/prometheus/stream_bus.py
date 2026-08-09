import asyncio
import logging
from collections.abc import AsyncIterator, Callable

logger = logging.getLogger(__name__)

MAX_BUFFER_EVENTS = 5000  # ponytail: hard cap; older events dropped, clients reconcile from history


class StreamChannel:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.task: asyncio.Task | None = None
        self.finished = False

    def publish(self, event: dict) -> None:
        self.events.append(event)
        if len(self.events) > MAX_BUFFER_EVENTS:
            del self.events[: len(self.events) - MAX_BUFFER_EVENTS]
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self.subscribers.discard(q)


class StreamBus:
    def __init__(self) -> None:
        self._channels: dict[str, StreamChannel] = {}

    def getOrCreate(self, sessionId: str) -> StreamChannel:
        ch = self._channels.get(sessionId)
        if ch is None:
            ch = StreamChannel()
            self._channels[sessionId] = ch
        return ch

    def publish(self, sessionId: str, event: dict) -> None:
        self.getOrCreate(sessionId).publish(event)

    def subscribe(self, sessionId: str, cursor: int = 0) -> tuple[asyncio.Queue, StreamChannel] | None:
        ch = self._channels.get(sessionId)
        if ch is None:
            return None
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        for event in ch.events[cursor:]:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                break
        ch.subscribers.add(q)
        return q, ch

    def unsubscribe(self, sessionId: str, q: asyncio.Queue) -> None:
        ch = self._channels.get(sessionId)
        if ch:
            ch.subscribers.discard(q)

    def startRun(self, sessionId: str, runner_factory: Callable[[], AsyncIterator[dict]]) -> None:
        ch = self.getOrCreate(sessionId)
        if ch.task:
            # cancel() on a finished task is a no-op, so this resets the log
            # for EVERY new run, not just ones replacing an active run.
            ch.task.cancel()
            ch.events.clear()
            ch.finished = False

        async def _run() -> None:
            try:
                async for event in runner_factory():
                    ch.publish(event)
            except asyncio.CancelledError:
                logger.info("Stream run cancelled for session %s", sessionId)
            except Exception:
                logger.exception("Stream run failed for session %s", sessionId)
            finally:
                if ch.task is asyncio.current_task():
                    ch.finished = True
                    ch.publish({"type": "done"})

        ch.task = asyncio.get_running_loop().create_task(_run())


streamBus = StreamBus()
