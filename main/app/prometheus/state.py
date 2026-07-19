import logging

logger = logging.getLogger(__name__)


class HarnessState:
    def __init__(self):
        self.data: dict = {}
        self._changed: bool = False

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value
        self._changed = True

    def toDict(self) -> dict:
        return dict(self.data)

    def toContext(self) -> str:
        if not self.data:
            return ""
        return "\n".join(f"- {k}: {v}" for k, v in self.data.items())

    def hasChanged(self) -> bool:
        return self._changed

    def resetChanged(self) -> bool:
        wasChanged = self._changed
        self._changed = False
        return wasChanged

    def clear(self) -> None:
        self.data.clear()
        self._changed = False
