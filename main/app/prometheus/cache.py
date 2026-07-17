"""ResultCache — SHA256-keyed file-based cache for computed results."""

import hashlib
import json
import time
from pathlib import Path


class ResultCache:
    """File-based cache keyed by SHA256 of code.

    Stores results as JSON under:
        {workspaceRoot}/{userId}/{sessionId}/computed/{hash}.json
    """

    def __init__(self, workspaceRoot: str) -> None:
        self._root = Path(workspaceRoot)

    def _cache_path(self, userId: int, sessionId: str, code: str) -> Path:
        h = hashlib.sha256(code.encode()).hexdigest()
        return self._root / str(userId) / sessionId / "computed" / f"{h}.json"

    def get(self, userId: int, sessionId: str, code: str) -> dict | None:
        """Return cached result dict or None if miss."""
        path = self._cache_path(userId, sessionId, code)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, userId: int, sessionId: str, code: str, result: dict) -> None:
        """Store result with timestamp."""
        path = self._cache_path(userId, sessionId, code)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "codeHash": hashlib.sha256(code.encode()).hexdigest(),
            "timestamp": time.time(),
            "result": result,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def invalidate(self, userId: int, sessionId: str) -> None:
        """Delete all cached results for a session."""
        session_dir = self._root / str(userId) / sessionId / "computed"
        if session_dir.exists():
            for f in session_dir.iterdir():
                if f.suffix == ".json":
                    f.unlink()

    def exists(self, userId: int, sessionId: str, code: str) -> bool:
        """Check if a result exists for the given code."""
        return self._cache_path(userId, sessionId, code).exists()
