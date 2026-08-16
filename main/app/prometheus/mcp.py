import logging
from config import Config
import time
import asyncio

from fastmcp import Client
from fastmcp.client.client import StreamableHttpTransport

logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL = 60

MCP_SERVERS = [
    {
        "name": "stocks",
        "url": f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}/stocks/mcp",
        "headers": {"X-MCP": "true"},
    },
    {"name": "searxng", "url": f"{Config.PROMETHEUS.SEARXNG_URL}/mcp/"},
]


def buildClient(server):
    url = server["url"]
    headers = server.get("headers", {})
    if headers:
        return Client(transport=StreamableHttpTransport(url, headers=headers))
    return Client(url)


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
                client = buildClient(server)
                await client.__aenter__()
                type(client.session).__deepcopy__ = lambda self, memo=None: self
                clients[name] = client
                logger.info("MCPClientPool: %s connected", name)
            except Exception as e:
                logger.error("MCPClientPool: %s connect failed: %s", name, e)

        self.clients = clients
        self.lastHealthCheck = time.time()
        logger.info("MCPClientPool: initialized with %s", list(clients.keys()))

    async def getClients(self):
        if self.clients is None:
            await self.initialize()
        if time.time() - self.lastHealthCheck > HEALTH_CHECK_INTERVAL:
            asyncio.create_task(self.healthCheck())
        return self.clients, [c.session for c in self.clients.values()]

    async def healthCheck(self):
        async with self.lock:
            if time.time() - self.lastHealthCheck < HEALTH_CHECK_INTERVAL:
                return
            self.lastHealthCheck = time.time()
            for name, client in self.clients.items():
                try:
                    await client.session.list_tools()
                except Exception as e:
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
            new = buildClient(server)
            await new.__aenter__()
            type(new.session).__deepcopy__ = lambda self, memo=None: self
            self.clients[name] = new
            logger.info("MCPClientPool: %s reconnected", name)
        except Exception as e:
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
