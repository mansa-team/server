"""SandboxManager — on-demand CubeSandbox (E2B-compatible) microVM manager.

Lifecycle: create → execute/upload_file/read_file → checkpoint → destroy.
Sandboxes are created ONLY when the LLM calls execute_code and only for
premium users. On failure the harness degrades to chat-only mode.
"""

import logging
import uuid
from typing import Any

import httpx

from config import Config

logger = logging.getLogger(__name__)


def _base_url():
    return f"http://{Config.PROMETHEUS.SANDBOX_HOST}:{Config.PROMETHEUS.SANDBOX_PORT}"


class SandboxManager:
    """Thin async wrapper around the CubeSandbox/E2B HTTP API.

    All methods are stateless classmethods — no instance needed.
    """

    @staticmethod
    async def create(userId: int, sessionId: str) -> str:
        """Create a sandbox and return its ID."""
        sandbox_id = f"sb-{userId}-{uuid.uuid4().hex[:8]}"
        async with httpx.AsyncClient(base_url=_base_url(), timeout=30) as client:
            resp = await client.post(
                "/sandboxes",
                json={
                    "sandboxId": sandbox_id,
                    "templateId": Config.PROMETHEUS.SANDBOX_TEMPLATE,
                    "metadata": {"userId": str(userId), "sessionId": sessionId},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            sandbox_id = data.get("sandboxId", sandbox_id)
            logger.info("Sandbox created: %s", sandbox_id)
            return sandbox_id

    @staticmethod
    async def execute(sandboxId: str, code: str) -> dict[str, Any]:
        """Execute Python code inside the sandbox. Returns {stdout, stderr}."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=120) as client:
            resp = await client.post(f"/sandboxes/{sandboxId}/executions", json={"code": code})
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def checkpoint(sandboxId: str, key: str) -> str:
        """Snapshot sandbox state via CubeCoW. Returns checkpoint ID."""
        cp_id = f"cp-{uuid.uuid4().hex[:8]}"
        async with httpx.AsyncClient(base_url=_base_url(), timeout=60) as client:
            resp = await client.post(
                f"/sandboxes/{sandboxId}/checkpoints",
                json={"checkpointId": cp_id, "key": key},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("checkpointId", cp_id)

    @staticmethod
    async def restore(checkpointId: str) -> str:
        """Restore a sandbox from a checkpoint. Returns new sandbox ID."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=60) as client:
            resp = await client.post(f"/checkpoints/{checkpointId}/restore")
            resp.raise_for_status()
            data = resp.json()
            return data.get("sandboxId", "")

    @staticmethod
    async def upload_file(sandboxId: str, path: str, content: bytes) -> bool:
        """Upload a file into the sandbox filesystem."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=30) as client:
            resp = await client.put(
                f"/sandboxes/{sandboxId}/files",
                json={"path": path, "content": content.decode("utf-8", errors="replace")},
            )
            return resp.status_code < 400

    @staticmethod
    async def read_file(sandboxId: str, path: str) -> str:
        """Read a file from the sandbox filesystem."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=30) as client:
            resp = await client.get(f"/sandboxes/{sandboxId}/files", params={"path": path})
            resp.raise_for_status()
            return resp.json().get("content", "")

    @staticmethod
    async def destroy(sandboxId: str) -> None:
        """Destroy a sandbox."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=15) as client:
            await client.delete(f"/sandboxes/{sandboxId}")


# ponytail: SandboxManager is a pure HTTP wrapper — no DB, no state.
# If CubeSandbox adds WebSocket streaming, wrap the client here.
