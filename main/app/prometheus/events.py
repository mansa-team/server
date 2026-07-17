import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class LoopLogger:
    def __init__(self, history: list):
        self._history = history

    def emit_tool_call(self, toolName: str, args: dict, *, turnNumber: int = 0):
        self._history.append(
            {
                "role": "loop_event",
                "eventType": "tool_call",
                "toolName": toolName,
                "metadata": {"args": args, "turnNumber": turnNumber},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def emit_tool_result(self, toolName: str, result: dict, *, turnNumber: int = 0):
        self._history.append(
            {
                "role": "loop_event",
                "eventType": "tool_result",
                "toolName": toolName,
                "metadata": {"result": result, "turnNumber": turnNumber},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def emit_turn_end(self, *, turnNumber: int = 0, durationMs: int = 0, toolsUsed: list | None = None):
        self._history.append(
            {
                "role": "loop_event",
                "eventType": "turn_end",
                "metadata": {"turnNumber": turnNumber, "durationMs": durationMs, "toolsUsed": toolsUsed or []},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def flush(self):
        pass
