import asyncio
import logging
from pathlib import Path
from config import SessionLocal

from forgevm import AsyncClient
from forgevm.exceptions import SandboxNotFound

from config import Config
from main.models.sandbox import PrometheusSandbox

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path("/data/workspaces")

userLocks: dict[int, asyncio.Lock] = {}


def lockFor(userId: int) -> asyncio.Lock:
    if userId not in userLocks:
        userLocks[userId] = asyncio.Lock()
    return userLocks[userId]


def getClient() -> AsyncClient:
    return AsyncClient(base_url=Config.PROMETHEUS["FORGEVM_URL"], timeout=30)


def hostPath(userId: int, sandboxPath: str) -> Path:
    rel = sandboxPath.lstrip("/")
    if rel == "workspace":
        rel = ""
    elif rel.startswith("workspace/"):
        rel = rel[len("workspace/"):]

    base = (WORKSPACE_ROOT / str(userId)).resolve(strict=False)
    candidate = (base / rel).resolve(strict=False)
    if not candidate.is_relative_to(base):
        raise ValueError("Invalid workspace path")
    return candidate


def sandboxPath(hostPath: Path, userId: int) -> str:
    rel = hostPath.relative_to(WORKSPACE_ROOT / str(userId))
    return f"/workspace/{rel}"


class SandboxManager:
    @staticmethod
    async def create(userId: int) -> str:
        client = getClient()
        try:
            sandbox = await client.spawn(
                image=Config.PROMETHEUS["SANDBOX_IMAGE"],
                memory_mb=Config.PROMETHEUS["SANDBOX_MEMORY"],
                vcpus=Config.PROMETHEUS["SANDBOX_CPU"],
                ttl=f"{Config.PROMETHEUS['SANDBOX_TTL']}m",
            )
            sandboxId = sandbox.id  # type: ignore[attr-defined]
            logger.info("Sandbox created: %s for user %d", sandboxId, userId)
            return sandboxId
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

    @staticmethod
    async def getOrCreate(userId: int, db) -> str:
        lock = lockFor(userId)
        async with lock:
            mapping = db.query(PrometheusSandbox).filter(PrometheusSandbox.userId == userId).first()

            if mapping:
                client = getClient()
                try:
                    sandbox = await client.get(mapping.sandboxId)
                    # ponytail: ForgeVM metadata can be stale — Docker may have
                    # killed the container but ForgeVM still reports state "running".
                    # Verify alive with a tiny exec. If it fails, the sandbox is dead.
                    await sandbox.extend_ttl(f"{Config.PROMETHEUS['SANDBOX_TTL']}m")
                    await sandbox.exec(command="echo", args=["ok"], timeout="3s")
                    logger.info("Reusing sandbox %s for user %d", mapping.sandboxId, userId)
                    return mapping.sandboxId
                except SandboxNotFound:
                    logger.info("Sandbox %s dead for user %d, creating new", mapping.sandboxId, userId)
                    db.delete(mapping)
                    db.commit()
                except Exception as e:
                    logger.warning("Error checking sandbox %s: %s, creating new", mapping.sandboxId, e)
                    db.delete(mapping)
                    db.commit()
                finally:
                    await client.close()

            sandboxId = await SandboxManager.create(userId)

            db.add(
                PrometheusSandbox(
                    userId=userId,
                    sandboxId=sandboxId,
                    workspacePath=f"/data/workspaces/{userId}",
                )
            )
            db.commit()
            logger.info("Mapped sandbox %s to user %d", sandboxId, userId)

            syncIn = await SandboxManager.syncToSandbox(sandboxId, userId)
            if syncIn:
                logger.info("Synced %d files to sandbox for user %d", syncIn, userId)

            return sandboxId

    @staticmethod
    async def execute(userId: int, code: str, sandboxId: str, timeout: int = 30, *, _retried: bool = False) -> dict:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)

            syncIn = await SandboxManager.syncToSandbox(sandboxId, userId)
            if syncIn:
                logger.debug("Synced %d files to sandbox before exec for user %d", syncIn, userId)

            result = await sandbox.exec(
                command="python3",
                args=["-c", code],
                timeout=f"{timeout}s",
            )
            output = {"stdout": result.stdout, "stderr": result.stderr}

            syncOut = await SandboxManager.syncFromSandbox(sandboxId, userId)
            if syncOut:
                logger.info("Synced %d files from sandbox for user %d", syncOut, userId)

            return output
        except SandboxNotFound:
            if _retried:
                raise
            logger.warning("Sandbox %s dead during exec for user %d, respawning", sandboxId, userId)
        finally:
            await client.close()

        db = SessionLocal()
        try:
            newId = await SandboxManager.getOrCreate(userId, db)
        finally:
            db.close()
        return await SandboxManager.execute(userId, code, newId, timeout, _retried=True)

    @staticmethod
    async def executeWithWorkspace(userId: int, code: str, timeout: int = 30) -> dict:
        lock = lockFor(userId)
        async with lock:
            sandboxId = await SandboxManager.create(userId)
            try:
                syncIn = await SandboxManager.syncToSandbox(sandboxId, userId)
                if syncIn:
                    logger.info("Synced %d files to sandbox for user %d", syncIn, userId)

                client = getClient()
                try:
                    sandbox = await client.get(sandboxId)
                    result = await sandbox.exec(
                        command="python3",
                        args=["-c", code],
                        timeout=f"{timeout}s",
                    )
                    output = {"stdout": result.stdout, "stderr": result.stderr}
                finally:
                    await client.close()

                syncOut = await SandboxManager.syncFromSandbox(sandboxId, userId)
                if syncOut:
                    logger.info("Synced %d files from sandbox for user %d", syncOut, userId)

                return output
            finally:
                await SandboxManager.destroy(sandboxId)

    @staticmethod
    def read_file(userId: int, path: str) -> str:
        host = hostPath(userId, path)
        if not host.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return host.read_text(encoding="utf-8")

    @staticmethod
    def write_file(userId: int, path: str, content: str) -> bool:
        try:
            host = hostPath(userId, path)
            host.parent.mkdir(parents=True, exist_ok=True)
            host.write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.warning("Failed to write %s: %s", path, e)
            return False

    @staticmethod
    def list_files(userId: int, path: str = "/workspace") -> dict:
        host = hostPath(userId, path)
        if not host.exists():
            return {"entries": []}
        entries = [str(sandboxPath(item, userId)) for item in sorted(host.rglob("*")) if item.is_file()]
        return {"entries": entries}

    @staticmethod
    async def syncToSandbox(sandboxId: str, userId: int) -> int:
        workspace = WORKSPACE_ROOT / str(userId)
        if not workspace.exists():
            return 0

        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            count = 0
            for item in workspace.rglob("*"):
                if item.is_file():
                    sandboxFilePath = f"/workspace/{item.relative_to(workspace)}"
                    await sandbox.write_file(sandboxFilePath, item.read_text(encoding="utf-8"))
                    count += 1
            return count
        finally:
            await client.close()

    @staticmethod
    async def syncFromSandbox(sandboxId: str, userId: int) -> int:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            paths: list[str] = await sandbox.glob_files("/workspace/**") or []
            count = 0
            for p in paths:
                try:
                    content = await sandbox.read_file(p)
                    host = hostPath(userId, p)
                    host.parent.mkdir(parents=True, exist_ok=True)
                    host.write_text(content, encoding="utf-8")
                    count += 1
                except Exception as e:
                    logger.warning("Failed to sync %s from sandbox: %s", p, e)
            return count
        finally:
            await client.close()
