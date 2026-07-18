import logging

logger = logging.getLogger(__name__)


class HarnessState:
    def __init__(self):
        self.data: dict = {}
        self.changed: bool = False

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value
        self.changed = True

    def to_dict(self) -> dict:
        return dict(self.data)

    def to_context(self) -> str:
        if not self.data:
            return ""
        return "\n".join(f"- {k}: {v}" for k, v in self.data.items())

    def haschanged(self) -> bool:
        return self.changed

    def resetchanged(self) -> bool:
        wasChanged = self.changed
        self.changed = False

        return wasChanged

    def clear(self) -> None:
        self.data.clear()
        self.changed = False
