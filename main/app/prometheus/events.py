"""LoopLogger — batched event logging for observable agent loops."""

import logging
from main.models.harness import LoopEvent

logger = logging.getLogger(__name__)


class LoopLogger:
    """Queue events during a loop, flush to DB at end."""

    def __init__(self, db):
        self._db = db
        self._queue: list[LoopEvent] = []

    def log(
        self,
        sessionId: str,
        eventType: str,
        *,
        userId: int | None = None,
        toolName: str | None = None,
        durationMs: int | None = None,
        metadata: dict | None = None,
    ):
        self._queue.append(
            LoopEvent(
                sessionId=sessionId,
                eventType=eventType,
                userId=userId,
                toolName=toolName,
                durationMs=durationMs,
                eventData=metadata,
            )
        )

    def emit(self, eventType: str, data: dict | None = None, **kwargs):
        """Log a generic event with optional metadata."""
        metadata = data or {}
        metadata.update(kwargs)
        self.log("", eventType, metadata=metadata if metadata else None)

    def emit_tool_call(self, toolName: str, args: dict, *, turnNumber: int = 0):
        """Log a tool invocation."""
        self.log("", "tool_call", toolName=toolName, metadata={"args": args, "turnNumber": turnNumber})

    def emit_tool_result(self, toolName: str, result: dict, *, turnNumber: int = 0):
        """Log a tool result."""
        self.log("", "tool_result", toolName=toolName, metadata={"result": result, "turnNumber": turnNumber})

    def emit_turn_end(self, *, turnNumber: int = 0, durationMs: int = 0, toolsUsed: list | None = None):
        """Log end of a turn with timing."""
        self.log(
            "", "turn_end", durationMs=durationMs, metadata={"turnNumber": turnNumber, "toolsUsed": toolsUsed or []}
        )

    def flush(self):
        if not self._queue:
            return
        try:
            self._db.add_all(self._queue)
            self._db.commit()
        except Exception:
            logger.exception("LoopLogger flush failed")
            self._db.rollback()
        finally:
            self._queue.clear()
