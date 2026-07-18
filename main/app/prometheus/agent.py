import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import Client
from google import genai
from google.genai import types
import google.genai._mcp_utils as _mcp

from config import Config
from main.models.memory import PrometheusMemory
from main.app.prometheus.chat import PrometheusChatManager
from main.app.prometheus.events import LoopLogger
from main.app.prometheus.sandbox import SandboxManager
from main.app.prometheus.state import HarnessState
from main.app.prometheus.tools import TOOL_REGISTRY, dispatchToolCall

_original_filter = _mcp._filter_to_supported_schema


def _safe_filter(schema):
    if not isinstance(schema, dict):
        return schema
    return _original_filter(schema)


_mcp._filter_to_supported_schema = _safe_filter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You're Prometheus, a investments assistant for Mansa, a Brazilian stock platform.

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

## Code Sandbox (On-Demand)
You have access to an isolated Python sandbox for quantitative analysis.
The sandbox is created automatically when you first call execute_code.

Use execute_code for: statistical analysis, DCF models, correlation matrices,
Monte Carlo simulations, custom charts, data transformations.

Use write_file to push data files (CSV, JSON) into the sandbox before running code.
Use read_file to read results from the sandbox.
Use list_files to explore the workspace.

Access stock data via MCP tools (get_fundamental, get_historical, get_cotations)
before running sandbox code — pass the data as variables in your code.

Libraries available: pandas, numpy, scipy, plotly, matplotlib, requests.
Save charts to /workspace/ as .html (plotly) or .png (matplotlib).
Always print() key findings so they appear in stdout.
"""


class Prometheus:
    def __init__(self):
        self.client = genai.Client(api_key=Config.PROMETHEUS["GEMINI_API.KEY"])

    @classmethod
    def buildSystemPrompt(cls, userId: int | None = None, db=None, state: HarnessState | None = None) -> str:
        memoryBlock = ""
        if userId and db:
            memories = (
                db.query(PrometheusMemory)
                .filter(PrometheusMemory.userId == userId)
                .filter(PrometheusMemory.archivedAt.is_(None))
                .order_by(PrometheusMemory.baseScore.desc())
                .limit(10)
                .all()
            )
            if memories:
                memoryBlock = "\n".join(f"- [{m.memoryType}] {m.memoryKey}: {m.memoryValue}" for m in memories)

        sections = [SYSTEM_PROMPT]
        if memoryBlock:
            sections.append(f"\n[MEMÓRIAS DO USUÁRIO]\n{memoryBlock}")
        if state and state.to_context():
            sections.append(f"\n[HARNESS STATE]\n{state.to_context()}\n[/HARNESS STATE]")
        return "".join(sections)

    @asynccontextmanager
    async def openMCPClients(self):
        stocks = Client(f"http://{Config.STOCKS_API['HOST']}:{Config.STOCKS_API['PORT']}/stocks/mcp")
        searxng = Client(f"{Config.PROMETHEUS['SEARXNG_URL']}/mcp/")
        async with stocks, searxng:
            for s in [stocks.session, searxng.session]:
                type(s).__deepcopy__ = lambda self, memo=None: self  # type: ignore[attr-defined]
            yield {"stocks": stocks, "searxng": searxng}, [stocks.session, searxng.session]

    def makeChat(self, sessions, history, *, system_prompt=None, disable_automatic_function_calling=False):
        all_tools = list(sessions) + list(TOOL_REGISTRY.values())
        kwargs = dict(system_instruction=system_prompt, tools=all_tools, temperature=0.5)
        if disable_automatic_function_calling:
            kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        return self.client.aio.chats.create(
            model="gemini-flash-lite-latest", history=history, config=types.GenerateContentConfig(**kwargs)
        )

    async def streamMessage(self, query=None, sessionId=None, db=None, user=None) -> AsyncIterator[dict]:
        history = PrometheusChatManager.getHistory(db, str(sessionId), limit=50)
        state = HarnessState()
        loop = LoopLogger(history)
        system_prompt = Prometheus.buildSystemPrompt(user.get("userId") if user else None, db, state=state)

        try:
            async with self.openMCPClients() as (mcpClients, sessions):
                chat = self.makeChat(
                    sessions, history, system_prompt=system_prompt, disable_automatic_function_calling=True
                )
                stream = await chat.send_message_stream(query)
                fullText = ""
                turn = 0

                while True:
                    chunks_text = ""
                    function_calls: list = []
                    async for chunk in stream:
                        if hasattr(chunk, "text") and chunk.text:
                            chunks_text += chunk.text
                            yield {"type": "text", "text": chunk.text}
                        if hasattr(chunk, "function_calls") and chunk.function_calls:
                            fcs = chunk.function_calls
                            function_calls.extend(fcs.values() if isinstance(fcs, dict) else fcs)
                    fullText += chunks_text

                    if not function_calls:
                        break

                    turn_start = int(__import__("time").time() * 1000)
                    tools_used = []
                    responses = []

                    sandbox_id = None
                    for fc in function_calls:
                        tools_used.append(fc.name)
                        loop.emit_tool_call(fc.name, fc.args or {}, turnNumber=turn)
                        yield {"type": "tool_call", "tool": fc.name, "args": fc.args or {}, "turn": turn}

                        if fc.name == "execute_code":
                            try:
                                sandbox_id = await SandboxManager.getOrCreate(user.get("userId", 0), db)
                                logger.info("Sandbox ready: %s", sandbox_id)
                            except Exception as e:
                                logger.warning("Sandbox creation failed: %s", e)
                                responses.append(
                                    types.Part.from_function_response(
                                        name=fc.name, response={"error": "Sandbox unavailable."}
                                    )
                                )
                                continue

                        result = await dispatchToolCall(fc, mcpClients, user=user, state=state, sandbox_id=sandbox_id)
                        loop.emit_tool_result(fc.name, result, turnNumber=turn)
                        yield {"type": "tool_result", "tool": fc.name, "result": result, "turn": turn}
                        responses.append(types.Part.from_function_response(name=fc.name, response=result))

                    if state.has_changed():
                        responses.append(
                            types.Part.from_text(text=f"\n[HARNESS STATE]\n{state.to_context()}\n[/HARNESS STATE]")
                        )
                        state.reset_changed()

                    loop.emit_turn_end(
                        turnNumber=turn,
                        durationMs=int(__import__("time").time() * 1000) - turn_start,
                        toolsUsed=tools_used,
                    )
                    yield {
                        "type": "turn_end",
                        "turn": turn,
                        "durationMs": int(__import__("time").time() * 1000) - turn_start,
                        "toolsUsed": len(tools_used),
                    }
                    turn += 1
                    stream = await chat.send_message_stream(responses)

            PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))
            if fullText:
                PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", fullText)
        finally:
            loop.flush()
