import time
import logging
import asyncio

from fastmcp import Client
from fastmcp.client.client import StreamableHttpTransport

from config import Config

logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL = 60


class MCPClientPool:
    instance = None
    clients = None
    lastHealthCheck = 0.0
    lock = asyncio.Lock()

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
        return cls.instance

    async def initialize(self):
        stocks = Client(
            transport=StreamableHttpTransport(
                f"http://{Config.STOCKS_API['HOST']}:{Config.STOCKS_API['PORT']}/stocks/mcp",
                headers={"X-MCP": "true"},
            )
        )
        searxng = Client(f"{Config.PROMETHEUS['SEARXNG_URL']}/mcp/")
        async with stocks, searxng:
            for s in [stocks.session, searxng.session]:
                type(s).__deepcopy__ = lambda self, memo=None: self
            self.clients = {"stocks": stocks, "searxng": searxng}
            self.lastHealthCheck = time.time()
            logger.info("MCPClientPool: initialized with stocks + searxng")

    async def getClients(self):
        if self.clients is None:
            await self.initialize()
        if time.time() - self.lastHealthCheck > HEALTH_CHECK_INTERVAL:
            asyncio.create_task(self.healthCheck())
        return self.clients, [self.clients["stocks"].session, self.clients["searxng"].session]

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
        try:
            if name == "stocks":
                new = Client(
                    transport=StreamableHttpTransport(
                        f"http://{Config.STOCKS_API['HOST']}:{Config.STOCKS_API['PORT']}/stocks/mcp",
                        headers={"X-MCP": "true"},
                    )
                )
            else:
                new = Client(f"{Config.PROMETHEUS['SEARXNG_URL']}/mcp/")
            async with new:
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
                    pass
            self.clients = None
