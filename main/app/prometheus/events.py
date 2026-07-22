import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class LoopLogger:
    def __init__(self, history: list):
        self._history = history

    def emit(self, eventType: str, **kwargs) -> dict:
        event = {
            "role": "loop_event",
            "eventType": eventType,
            "metadata": kwargs,
            "timestamp": datetime.now().isoformat(),
        }
        self._history.append(event)
        return event
