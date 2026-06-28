from config import Config
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastmcp import Client
from google import genai
from google.genai import types
import google.genai._mcp_utils as _mcp

from main.app.prometheus.chat import PrometheusChatManager

_original_filter = _mcp._filter_to_supported_schema


def _safe_filter(schema):
    if not isinstance(schema, dict):
        return schema
    return _original_filter(schema)


_mcp._filter_to_supported_schema = _safe_filter

logger = logging.getLogger(__name__)


class Prometheus:
    def __init__(self):
        self.client = genai.Client(api_key=Config.PROMETHEUS["GEMINI_API.KEY"])
        self.updateDates()

    def updateDates(self):
        if Config.DEBUG_MODE:
            self.currentDate = "23/03/2026"
            self.currentISODate = "2026-03-23"
            self.currentYear = 2026
            self.lastYear = 2025
        else:
            now = datetime.now()
            self.currentDate = (now - timedelta(days=1)).strftime("%d/%m/%Y")
            self.currentISODate = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            self.currentYear = now.year
            self.lastYear = self.currentYear - 1

    @asynccontextmanager
    async def chatSession(self, history):
        systemPrompt = """
        You're a investments assistant.
        """

        stocks = Client(f"http://{Config.STOCKS_API['HOST']}:{Config.STOCKS_API['PORT']}/stocks/mcp")
        searxng = Client(f"http://{Config.PROMETHEUS['SEARXNG_HOST']}:{Config.PROMETHEUS['SEARXNG_PORT']}/mcp/")

        async with stocks, searxng:
            for s in [stocks.session, searxng.session]:
                type(s).__deepcopy__ = lambda self, memo=None: self  # type: ignore[attr-defined]

            yield self.client.aio.chats.create(
                model="gemini-flash-lite-latest",
                history=history,
                config=types.GenerateContentConfig(
                    system_instruction=systemPrompt,
                    tools=[stocks.session, searxng.session],
                    temperature=0.5,
                ),
            )

    async def sendMessage(self, query: str | None = None, sessionId: str | None = None, db=None):
        logger.info(f"Query: {query}")
        history = PrometheusChatManager.getHistory(db, str(sessionId), limit=50)

        async with self.chatSession(history) as chat:
            response = await chat.send_message(query)

        PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))
        PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", response.text)

        return response.text

    async def streamMessage(
        self, query: str | None = None, sessionId: str | None = None, db=None
    ) -> AsyncIterator[dict]:
        logger.info(f"Stream query: {query}")
        history = PrometheusChatManager.getHistory(db, str(sessionId), limit=50)

        full_text = ""
        async with self.chatSession(history) as chat:
            async for chunk in await chat.send_message_stream(query):
                if hasattr(chunk, "text") and chunk.text:
                    full_text += chunk.text
                    yield {"type": "text", "text": chunk.text}

        PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))
        PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", full_text)
