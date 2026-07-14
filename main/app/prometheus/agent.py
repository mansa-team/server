from config import Config
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import Client
from google import genai
from google.genai import types
import google.genai._mcp_utils as _mcp

from main.models.memory import UserMemory
from main.app.prometheus.chat import PrometheusChatManager
from main.app.prometheus.tools import MEMORY_TOOLS, dispatchToolCall

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

    SYSTEM_PROMPT = """
        You're a investments assistant for Mansa, a Brazilian stock platform.

        When presenting data, use rich UI tags to make responses visual and scannable.

        ## Available Tags

        ### Stat — single KPI card
        {% stat %}
        {"label": "P/L", "value": "5.2x", "change": "-0.3", "trend": "down", "description": "Price to Earnings ratio"}
        {% /stat %}
        Props: label (required), value (required), change (optional: "+12%", "-3%"), trend (optional: "up"/"down"), description (optional)

        ### Table — data grid
        {% table %}
        {"headers": ["Ticker", "P/L", "ROE"], "rows": [["PETR4", "5.2x", "15%"], ["VALE3", "3.1x", "22%"]], "caption": "Valuation Comparison"}
        {% /table %}
        Props: headers (required), rows (required), caption (optional)

        ### Chart — data visualization
        {% chart %}
        {"type": "line", "title": "PETR4 Price History", "x": ["Jan", "Feb", "Mar"], "y": [28.5, 29.1, 30.2]}
        {% /chart %}
        Types: "bar", "line", "pie", "donut". Props: type (required), x (labels, required), y (values, required), title (optional)

        ### Grid — multi-column layout
        {% grid %}
        {"cols": 3, "gap": "md", "items": [1, 2, 3]}
        {% /grid %}
        Use with stat cards inside for portfolio snapshots.

        ### Card — bordered container
        {% card %}
        {"title": "PETR4 Overview"}
        ...content inside...
        {% /card %}

        ### Tabs — tabbed sections
        {% tabs %}
        {"labels": ["Overview", "Financials", "Peers"]}
        {% /tab %}{% tab %}{"label": "Overview"}...{% /tab %}
        {% /tabs %}

        ### Accordion — collapsible section
        {% accordion %}
        {"title": "Methodology", "open": false}
        ...content inside...
        {% /accordion %}

        ### Progress — progress bar
        {% progress %}
        {"value": 75, "max": 100, "label": "Target Allocation"}
        {% /progress %}

        ### Divider — separator
        {% divider /%}

        ## Rules
        - Use {% stat %} for single metrics (P/L, ROE, DY, current price, market cap)
        - Use {% table %} when comparing multiple stocks side by side
        - Use {% chart %} for price history, trends, time series, sector allocation
        - Use {% grid %} + {% stat %} for dashboard-style multi-metric layouts (3-col grid of stat cards)
        - Use {% tabs %} to organize multi-view responses (Overview / Financials / Peers)
        - Use {% accordion %} for methodology notes, risk disclaimers, long explanations
        - Use {% progress %} for allocation %, portfolio weight vs target
        - Use {% card %} to group related content with a title
        - Wrap tag content in valid JSON, no extra text inside tags
        - You can mix prose and tags freely
        - Always use tags when presenting structured data — never dump raw JSON
        """

    @classmethod
    def buildSystemPrompt(cls, userId: int | None = None, db=None) -> str:
        memoryBlock = ""
        if userId and db:
            memories = (
                db.query(UserMemory)
                .filter(UserMemory.userId == userId)
                .filter(UserMemory.archivedAt.is_(None))
                .order_by(UserMemory.baseScore.desc())
                .limit(10)
                .all()
            )
            if memories:
                lines = [f"- [{m.memoryType}] {m.memoryKey}: {m.memoryValue}" for m in memories]
                memoryBlock = "\n".join(lines)

        memoriesSection = f"\n[MEMÓRIAS DO USUÁRIO]\n{memoryBlock}" if memoryBlock else ""
        return f"{cls.SYSTEM_PROMPT}{memoriesSection}"

    @asynccontextmanager
    async def openMCPClients(self):
        stocks = Client(f"http://{Config.STOCKS_API['HOST']}:{Config.STOCKS_API['PORT']}/stocks/mcp")
        searxng = Client(f"http://{Config.PROMETHEUS['SEARXNG_HOST']}:{Config.PROMETHEUS['SEARXNG_PORT']}/mcp/")
        async with stocks, searxng:
            for s in [stocks.session, searxng.session]:
                type(s).__deepcopy__ = lambda self, memo=None: self  # type: ignore[attr-defined]
            yield {"stocks": stocks, "searxng": searxng}, [stocks.session, searxng.session]

    def makeChat(self, sessions, history, *, system_prompt=None, disable_automatic_function_calling=False):
        prompt = system_prompt or self.SYSTEM_PROMPT
        all_tools = list(sessions) + MEMORY_TOOLS
        kwargs = dict(
            system_instruction=prompt,
            tools=all_tools,
            temperature=0.5,
        )
        if disable_automatic_function_calling:
            kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        return self.client.aio.chats.create(
            model="gemini-flash-lite-latest",
            history=history,
            config=types.GenerateContentConfig(**kwargs),
        )

    async def sendMessage(
        self, query: str | None = None, sessionId: str | None = None, db=None, user: dict | None = None
    ):
        logger.info(f"Query: {query}")
        history = PrometheusChatManager.getHistory(db, str(sessionId), limit=50)
        PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))
        system_prompt = Prometheus.buildSystemPrompt(user.get("userId") if user else None, db)

        async with self.openMCPClients() as (clients, sessions):
            chat = self.makeChat(sessions, history, system_prompt=system_prompt)
            response = await chat.send_message(query)

        PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", response.text)
        return response.text

    async def streamMessage(
        self, query: str | None = None, sessionId: str | None = None, db=None, user: dict | None = None
    ) -> AsyncIterator[dict]:
        logger.info(f"Stream query: {query}")
        history = PrometheusChatManager.getHistory(db, str(sessionId), limit=50)

        fullText = ""
        system_prompt = Prometheus.buildSystemPrompt(user.get("userId") if user else None, db)

        async with self.openMCPClients() as (mcpClients, sessions):
            chat = self.makeChat(
                sessions, history, system_prompt=system_prompt, disable_automatic_function_calling=True
            )

            try:
                stream = await chat.send_message_stream(query)

                while True:
                    functionCalls: list = []

                    async for chunk in stream:
                        if hasattr(chunk, "text") and chunk.text:
                            fullText += chunk.text
                            yield {"type": "text", "text": chunk.text}

                        if hasattr(chunk, "function_calls") and chunk.function_calls:
                            fcs = chunk.function_calls
                            if isinstance(fcs, dict):
                                functionCalls.extend(fcs.values())
                            elif isinstance(fcs, (list, tuple)):
                                functionCalls.extend(fcs)

                    if not functionCalls:
                        break

                    functionResponses = []
                    for fc in functionCalls:
                        result = await dispatchToolCall(fc, mcpClients, user=user)
                        functionResponses.append(
                            types.Part.from_function_response(
                                name=fc.name,
                                response=result,
                            )
                        )
                    stream = await chat.send_message_stream(functionResponses)
            finally:
                PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))
                if fullText:
                    PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", fullText)
