import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class LoopLogger:
    def __init__(self, history: list):
        self.history = history

    def emit(self, eventType: str, **kwargs) -> dict:
        event = {
            "role": "loop_event",
            "eventType": eventType,
            "metadata": kwargs,
            "timestamp": datetime.now().isoformat(),
        }
        self.history.append(event)
        return event
