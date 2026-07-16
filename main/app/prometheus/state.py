import logging

logger = logging.getLogger(__name__)


class HarnessState:
    """In-memory state dict that persists across loop iterations within a single request.

    The LLM manages this via get_state / set_state tools. State is injected
    into context after function rounds when changed. Dies with the request.
    """

    def __init__(self):
        self._data: dict = {}
        self._changed: bool = False

    def get(self, key: str, default=None):
        """Retrieve a value from state. Returns default if key not found."""
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """Store a value in state. Marks state as changed for context injection."""
        self._data[key] = value
        self._changed = True

    def to_dict(self) -> dict:
        """Return a copy of the current state."""
        return dict(self._data)

    def to_context(self) -> str:
        """Format state as a string for injection into the LLM context."""
        if not self._data:
            return ""
        return "\n".join(f"- {k}: {v}" for k, v in self._data.items())

    def has_changed(self) -> bool:
        """Check if state changed since last reset."""
        return self._changed

    def reset_changed(self) -> bool:
        """Reset the changed flag. Returns the previous state."""
        was_changed = self._changed
        self._changed = False
        return was_changed

    def clear(self) -> None:
        """Clear all state data."""
        self._data.clear()
        self._changed = False
