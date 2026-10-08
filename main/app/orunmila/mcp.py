import logging
import time
import asyncio

from config import Config

from fastmcp import Client
from fastmcp.client.client import StreamableHttpTransport

logger = logging.getLogger(__name__)


def getLoopbackHeaders(db=None) -> dict:
    """Fresh X-Service-Token per pool (re)connect, never import-time.

    Mints an opaque service session row (rotation without restart is revoke).
    Empty dict when the DB is unreachable: the pool logs and connects without
    the wallet entry rather than holding a static restart-to-rotate token.
    """
    try:
        from config import SessionLocal
        from main.app.authentication.service_token import createServiceToken

        session = db if db is not None else SessionLocal()
        try:
            return {"X-Service-Token": createServiceToken(session)}
        finally:
            if db is None:
                session.close()
    except Exception as exc:
        logger.warning("MCPClientPool: loopback mint failed: %s", exc)
        return {}


def prepareServer(server, db=None):
    if not server.get("service_loopback"):
        return server
    return {**server, "headers": {**server.get("headers", {}), **getLoopbackHeaders(db)}}


MCP_SERVERS = [
    {
        "name": "stocks",
        "url": f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}/stocks/mcp",
        "headers": {"X-MCP": "true"},
    },
    {"name": "searxng", "url": f"{Config.ORUNMILA.SEARXNG_URL}/mcp/"},
    {
        "name": "wallet",
        "url": f"http://{Config.USER.HOST}:{Config.USER.PORT}/wallet/mcp",
        "service_loopback": True,
    },
]


def buildClient(server):
    url = server["url"]
    headers = server.get("headers", {})
    if headers:
        return Client(transport=StreamableHttpTransport(url, headers=headers))
    return Client(url)


async def connect(server):
    client = buildClient(server)
    await client.__aenter__()
    type(client.session).__deepcopy__ = lambda self, memo=None: self
    return client


class MCPClientPool:
    def __init__(self):
        self.clients = None
        self.lastHealthCheck = 0.0
        self.lock = asyncio.Lock()

    async def initialize(self):
        clients = {}
        for server in MCP_SERVERS:
            name = server["name"]
            try:
                clients[name] = await connect(prepareServer(server))
                logger.info("MCPClientPool: %s connected", name)
            except (OSError, TimeoutError, ConnectionError, RuntimeError, ValueError) as e:
                logger.error("MCPClientPool: %s connect failed: %s", name, e)

        self.clients = clients
        self.lastHealthCheck = time.time()
        logger.info("MCPClientPool: initialized with %s", list(clients.keys()))

    async def getClients(self):
        if self.clients is None:
            await self.initialize()
        if time.time() - self.lastHealthCheck > 60:
            asyncio.create_task(self.healthCheck())
        return self.clients, [c.session for c in self.clients.values()]

    async def healthCheck(self):
        async with self.lock:
            if time.time() - self.lastHealthCheck < 60:
                return
            self.lastHealthCheck = time.time()
            for name, client in self.clients.items():
                try:
                    await client.session.list_tools()
                except (OSError, TimeoutError, ConnectionError, RuntimeError, ValueError) as e:
                    logger.warning("MCPClientPool: %s unhealthy, reconnecting: %s", name, e)
                    await self.reconnect(name)

    async def reconnect(self, name):
        servers = {s["name"]: s for s in MCP_SERVERS}
        server = servers.get(name)
        if not server:
            logger.error("MCPClientPool: %s not found in MCP_SERVERS", name)
            return
        try:
            if name in self.clients:
                await self.clients[name].__aexit__(None, None, None)
            new = await connect(prepareServer(server))
            self.clients[name] = new
            logger.info("MCPClientPool: %s reconnected", name)
        except (OSError, TimeoutError, ConnectionError, RuntimeError, ValueError) as e:
            logger.error("MCPClientPool: %s reconnect failed: %s", name, e)

    async def close(self):
        if self.clients:
            for client in self.clients.values():
                try:
                    await client.__aexit__(None, None, None)
                except Exception:
                    pass  # nosec: B110 best-effort per-client cleanup
            self.clients = None


clientPool = MCPClientPool()
