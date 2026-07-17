import logging

from forgevm import AsyncClient, ExecResult

from config import Config

logger = logging.getLogger(__name__)

FORGEVM_URL = Config.PROMETHEUS.get("FORGEVM_URL", "http://forgevm:7423")
WORKSPACE_ROOT = Config.PROMETHEUS.get("WORKSPACE_ROOT", "/data/workspaces")
SANDBOX_IMAGE = Config.PROMETHEUS.get("SANDBOX_IMAGE", "python:3.12-slim")
SANDBOX_MEMORY_MB = Config.PROMETHEUS.get("SANDBOX_MEMORY_MB", 2048)
SANDBOX_CPUS = Config.PROMETHEUS.get("SANDBOX_CPUS", 2)
SANDBOX_TTL_MINUTES = Config.PROMETHEUS.get("SANDBOX_TTL_MINUTES", 30)


def getClient() -> AsyncClient:
    return AsyncClient(base_url=FORGEVM_URL, timeout=30)


class SandboxManager:
    @staticmethod
    async def create(userId: int) -> str:
        client = getClient()
        try:
            sandbox = await client.spawn(
                image=SANDBOX_IMAGE,
                memory_mb=SANDBOX_MEMORY_MB,
                vcpus=SANDBOX_CPUS,
                ttl=f"{SANDBOX_TTL_MINUTES}m",
            )
            sandbox_id = sandbox.id  # type: ignore[attr-defined]
            logger.info("Sandbox created: %s for user %d", sandbox_id, userId)
            return sandbox_id
        finally:
            await client.close()

    @staticmethod
    async def execute(sandboxId: str, code: str, timeout: int = 30) -> dict:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            result: ExecResult = await sandbox.exec(
                command="python3",
                args=["-c", code],
                timeout=f"{timeout}s",
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        finally:
            await client.close()

    @staticmethod
    async def read_file(sandboxId: str, path: str) -> str:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            return await sandbox.read_file(path)
        finally:
            await client.close()

    @staticmethod
    async def write_file(sandboxId: str, path: str, content: str) -> bool:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            await sandbox.write_file(path, content)
            return True
        except Exception:
            return False
        finally:
            await client.close()

    @staticmethod
    async def list_files(sandboxId: str, path: str = "/workspace") -> dict:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            entries = await sandbox.list_files(path)
            return {"entries": entries}
        finally:
            await client.close()

    @staticmethod
    async def destroy(sandboxId: str) -> None:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            await sandbox.destroy()
            logger.info("Sandbox destroyed: %s", sandboxId)
        except Exception as e:
            logger.warning("Failed to destroy sandbox %s: %s", sandboxId, e)
        finally:
            await client.close()
