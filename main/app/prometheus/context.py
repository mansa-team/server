"""ToolContext — bundles all dependencies for tool execution.

Replace passing user, state, mcpClients individually to every tool.
New sandbox/cache tools receive a single ctx: ToolContext parameter instead.
Existing tools (search_memory, save_memory, get_state, set_state) keep their
current signatures — ToolContext is for NEW tools only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from main.app.prometheus.cache import ResultCache
    from main.app.prometheus.sandbox import SandboxManager
    from main.app.prometheus.state import HarnessState


@dataclass
class ToolContext:
    """Single dependency bundle for tool execution.

    Created once per request in agent.py and passed to all tools.
    Existing memory/state tools keep their current signatures.
    New sandbox/cache tools receive this instead of individual params.
    """

    user: dict[str, Any] | None = None
    state: HarnessState | None = None
    sandbox: Any = None  # SandboxManager — Any to avoid import at module level
    cache: Any = None  # ResultCache — Any to avoid import at module level
    mcpClients: dict[str, Any] = field(default_factory=dict)
    userId: int | None = None
    sessionId: str | None = None

    def __post_init__(self) -> None:
        """Extract userId from user dict if not explicitly set."""
        if self.userId is None and self.user is not None:
            self.userId = self.user.get("userId")
