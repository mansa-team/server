import logging

logger = logging.getLogger(__name__)


class HarnessState:
    def __init__(self):
        self._data: dict = {}
        self._changed: bool = False

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._changed = True

    def to_dict(self) -> dict:
        return dict(self._data)

    def to_context(self) -> str:
        if not self._data:
            return ""
        return "\n".join(f"- {k}: {v}" for k, v in self._data.items())

    def has_changed(self) -> bool:
        return self._changed

    def reset_changed(self) -> bool:
        was_changed = self._changed
        self._changed = False

        return was_changed

    def clear(self) -> None:
        self._data.clear()
        self._changed = False
