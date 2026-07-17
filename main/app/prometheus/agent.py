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
from main.app.prometheus.tools import TOOL_REGISTRY, dispatchToolCall
from main.app.prometheus.state import HarnessState
from main.app.prometheus.cache import ResultCache
from main.app.prometheus.events import LoopLogger
from main.app.prometheus.sandbox import SandboxManager

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

        ## Code Sandbox (On-Demand)
        You have access to an isolated Python sandbox for quantitative analysis.
        The sandbox is created automatically when you first call execute_code.
        Only available for premium users.

        Use execute_code for: statistical analysis, DCF models, correlation matrices,
        Monte Carlo simulations, custom charts, data transformations.

        Access stock data via MCP tools (get_fundamental, get_historical, get_cotations)
        before running sandbox code — pass the data as variables in your code.

        Libraries available: pandas, numpy, scipy, plotly, matplotlib, requests.
        Save charts to /tmp/ as .html (plotly) or .png (matplotlib).
        Always print() key findings so they appear in stdout.

        ## Result Cache
        Before executing expensive code, check the cache with check_cache(code_hash).
        If hit, use the cached result instead of re-executing.
        The cache is automatic — same code + same inputs = cache hit.

        ## Harness State
        You have access to an in-memory state that persists across tool calls within this conversation.
        Use set_state to save important values: intermediate results, analysis progress, user preferences.
        Use get_state to recall values you saved earlier.

        Guidelines:
        - At the start of a multi-step analysis, save the user's goal: set_state("goal", "...")
        - After each major data fetch, save the result: set_state("petr4_fundamental", "...")
        - Track your progress: set_state("step", "3/8 computing correlation")
        - Before responding, check if you have saved context to recall

        ## Memory Sync
        After completing a complex analysis or when you learn something important about the user,
        call save_memory to persist it across sessions. This is separate from the harness state —
        state is temporary (this request only), memory is permanent (all sessions).
        """

    @classmethod
    def buildSystemPrompt(cls, userId: int | None = None, db=None, state: HarnessState | None = None) -> str:
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

        stateSection = ""
        if state and state.to_context():
            stateSection = f"\n[HARNESS STATE]\n{state.to_context()}\n[/HARNESS STATE]"

        return f"{cls.SYSTEM_PROMPT}{memoriesSection}{stateSection}"

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
        all_tools = list(sessions) + list(TOOL_REGISTRY.values())

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

        state = HarnessState()
        system_prompt = Prometheus.buildSystemPrompt(user.get("userId") if user else None, db, state=state)

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
        state = HarnessState()
        loop = LoopLogger(db)
        cache = ResultCache(workspaceRoot=Config.PROMETHEUS.get("WORKSPACE_ROOT", "/tmp/prometheus-workspace"))

        # On-demand sandbox: created ONLY when LLM calls execute_code
        is_premium = user and user.get("isPremium", False)
        sandbox_id = None

        system_prompt = Prometheus.buildSystemPrompt(user.get("userId") if user else None, db, state=state)

        try:
            loop.emit("turn_start", {"query": str(query)}, turnNumber=0)

            async with self.openMCPClients() as (mcpClients, sessions):
                chat = self.makeChat(
                    sessions,
                    history,
                    system_prompt=system_prompt,
                    disable_automatic_function_calling=True,
                )

                try:
                    stream = await chat.send_message_stream(query)
                    turnNumber = 0

                    while True:
                        functionCalls: list = []
                        toolsUsed: list = []
                        turnStartMs = __import__("time").time() * 1000

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
                            toolsUsed.append(fc.name)
                            toolStartMs = __import__("time").time() * 1000
                            loop.emit_tool_call(fc.name, fc.args or {}, turnNumber=turnNumber)

                            # On-demand sandbox creation: only when LLM calls execute_code
                            if fc.name == "execute_code" and sandbox_id is None:
                                if is_premium:
                                    try:
                                        sandbox_id = await SandboxManager.create(user.get("userId", 0), str(sessionId))
                                        logger.info(f"On-demand sandbox created: {sandbox_id}")
                                    except Exception as e:
                                        logger.warning(f"Sandbox creation failed: {e}")
                                        result = {"error": "Sandbox unavailable. Running in chat-only mode."}
                                        functionResponses.append(
                                            types.Part.from_function_response(name=fc.name, response=result)
                                        )
                                        continue
                                else:
                                    result = {"error": "Sandbox requires premium subscription. Upgrade to run code."}
                                    functionResponses.append(
                                        types.Part.from_function_response(name=fc.name, response=result)
                                    )
                                    continue

                            result = await dispatchToolCall(
                                fc,
                                mcpClients,
                                user=user,
                                state=state,
                                sandbox_id=sandbox_id,
                                cache=cache,
                            )

                            toolDuration = int(__import__("time").time() * 1000 - toolStartMs)
                            loop.emit_tool_result(fc.name, result, turnNumber=turnNumber)

                            functionResponses.append(types.Part.from_function_response(name=fc.name, response=result))

                        # Inject state if changed
                        if state.has_changed():
                            stateContext = state.to_context()
                            functionResponses.append(
                                types.Part.from_text(f"\n[HARNESS STATE]\n{stateContext}\n[/HARNESS STATE]")
                            )
                            state.reset_changed()

                        turnDuration = int(__import__("time").time() * 1000 - turnStartMs)
                        loop.emit_turn_end(
                            turnNumber=turnNumber,
                            durationMs=turnDuration,
                            toolsUsed=toolsUsed,
                        )
                        turnNumber += 1

                        stream = await chat.send_message_stream(functionResponses)
                finally:
                    PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))
                    if fullText:
                        PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", fullText)
        finally:
            # Cleanup: destroy sandbox, take checkpoint for premium users
            if sandbox_id:
                try:
                    if is_premium:
                        await SandboxManager.checkpoint(sandbox_id, f"session-{sessionId}")
                        logger.info(f"Checkpoint taken for sandbox {sandbox_id}")
                    await SandboxManager.destroy(sandbox_id)
                except Exception as e:
                    logger.warning(f"Sandbox cleanup failed: {e}")
            loop.flush()
