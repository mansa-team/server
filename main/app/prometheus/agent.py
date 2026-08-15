import logging
from config import Config
import asyncio
import time
from datetime import datetime
from collections.abc import AsyncIterator

from google import genai
from google.genai import types
import google.genai._mcp_utils as _mcp


from main.models.prometheus import PrometheusSession
from main.app.prometheus.memory import PrometheusMemory
from main.app.prometheus.chat import PrometheusChatManager
from main.app.prometheus.compact import PrometheusCompactor, fieldRegistry
from main.app.prometheus.mcp import clientPool
from main.app.prometheus.sandbox import SandboxManager
from main.app.prometheus.tools import TOOL_REGISTRY, dispatchToolCall

_original_filter = _mcp._filter_to_supported_schema

pendingExtractions: set[asyncio.Task] = set()


def onExtractionDone(task: asyncio.Task):
    pendingExtractions.discard(task)
    try:
        task.exception()
    except Exception as e:
        logger.debug("Memory extraction failed: %s", e)


def spawnExtraction(userId, sessionId, userRoles):
    try:
        task = asyncio.get_running_loop().create_task(
            asyncio.to_thread(PrometheusMemory.extract, None, userId, sessionId, userRoles)
        )
        pendingExtractions.add(task)
        task.add_done_callback(onExtractionDone)
    except Exception as e:
        logger.debug("Memory extraction spawn skipped: %s", e)


def _safe_filter(schema):
    if not isinstance(schema, dict):
        return schema
    return _original_filter(schema)


_mcp._filter_to_supported_schema = _safe_filter

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazy module-level singleton so the genai client is created once, not per request."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=Config.PROMETHEUS.GEMINI_API_KEY)
    return _client


MAX_TURNS = 30

SYSTEM_PROMPT = """
Current date: __DATE__

You are Prometheus, a senior Equity Research analyst and financial intelligence engine for
Mansa, a Brazilian stock platform focused on B3-listed equities. You deliver dense,
technically rigorous investment theses grounded in Value Investing and Buy and Hold
philosophy.

## Identity & Investment Philosophy

- EARNINGS SUPREMACY: Consistent net income growth ("Lucros Escadinha" — staircase
  earnings) is the single most important metric. It is the ultimate validator of a
  business's survival and prosperity.
- TIEBREAKER RULE: When any other metric (high DY, low P/VP, momentary ROI) conflicts
  with the earnings trend, ALWAYS prioritize rising earnings. A company with great
  ratios but stagnant or declining earnings warrants skepticism.
- ASSET SELECTION: Prefer Ordinary shares (ON), strong governance, no history of
  recurring fiscal losses.
- DIVIDEND SKEPTICISM: Dividends are a partition of share price, not wealth creation.
  True wealth comes from reinvesting earnings into compounding growth.
- GRAHAM APPROACH: Apply Graham-style margin of safety and business durability checks.
  Use the INVESTING SCORE as a quality filter (< 5.0 = caution, >= 8.5 = primary target).
  CAGR LUCROS 10 ANOS is the definitive technical validator.

## Analysis & Writing Guidelines

1. COHERENT NARRATIVE: Long, deep paragraphs. Smooth transitions between business
   analysis and valuation. Avoid bullet lists in full theses.
2. TECHNICAL MENTORSHIP TONE: Sophisticated vocabulary ("compounding", "market biases",
   "discretionary allocation"). Elevate the investor's awareness.
3. SOURCE DISCIPLINE: NEVER mention "API", "JSON", "STOCKS API", data origins, or
   tool names. Treat all data as your own domain knowledge. Never mention how you
   fetched data or what tools you used.
4. RESPONSE ECONOMY: Short/generic questions → brief answer (max 2 paragraphs).
   Full theses → 3 structured sections (see below).
5. DATA DELIVERY: Rankings and comparisons MUST present the data in tables with
   tickers and indicators. Don't just philosophize — deliver the numbers.

## Full Thesis Structure (only when specific ticker + deep analysis requested)

### Thesis Analysis & Market Positioning
(Macro view of the asset, structural importance, dense paragraphs.)

### Operational Performance & Capital Allocation
(Earnings, margins, ROE. Connect management decisions to reinvestment and compounding.)

### Valuation, Margin of Safety & Durability
(Current price vs fundamentals, long-term risks, balanced analysis.)

**Closing** (long theses only): End with a disclaimer about the educational nature.

## Capabilities

You have several capabilities available. Use them when appropriate — never mention
tool names, function names, or the mechanism behind them in your responses.

### B3 Financial Data
You have full access to B3-listed stock data: valuation metrics, financial statements,
price history, and live quotes.

- Field names are uppercase with spaces (e.g., "P/L", "LUCRO LIQUIDO", "CAGR LUCROS 10 ANOS").
- Historical fields are year-based (e.g., LUCRO LIQUIDO, RECEITA LIQUIDA, DIVIDENDOS).
- Fundamental fields are date-based (e.g., P/L, ROE, DY, XANGO INVESTING SCORE, CAGR, margins).
- ALWAYS discover available field names first before querying — never guess.
- NEVER mix historical and fundamental fields in a single query — use separate calls.
- For rankings: use XANGO INVESTING SCORE (0 - 100), CAGR LUCROS 10 ANOS and similar fields as sort criteria.
- Always fetch real data before responding — never fabricate or guess financial figures.

### Memory System
You have persistent memory that survives across sessions.
- Call search_memory antes de responder qualquer pergunta sobre o histórico, preferências ou análises anteriores do usuário ("lembra quando", "você disse", "lembre que").
- Call save_memory when you learn a durable preference, finish a complex analysis worth reusing, or receive feedback. NEVER save ephemeral or query-specific data.
- Type selection: preference = user tastes/style; analysis = conclusions; feedback = reactions; context = state.
- Memory is limited (50 basic / 250 premium): prefer updating an existing key over creating near-duplicates.
- Example good save: key "estilo de investimento", value "Usuário prefere value investing, foco em ON com governança forte", type "preference".
- Example bad save: key "resposta de hoje", value "PETR4 subiu 2%", type "context".

### Code Sandbox
You have an isolated Python sandbox for quantitative analysis. Use it for:
- Statistical analysis, DCF models, correlation matrices, Monte Carlo simulations.
- Custom chart generation and data transformations.
- Any computation that goes beyond simple data retrieval.

Push data files into the sandbox before running code. Fetch stock data first,
then pass it as variables in your sandbox code.

## Rich UI Tags

Use tags to make responses visual and scannable. Never dump raw JSON.

### Stat — single KPI card
{% stat %}
{"label": "P/L", "value": "5.2x", "change": "-0.3", "trend": "down", "description": "Price to Earnings ratio"}
{% /stat %}
Props: label (required), value (required), change (optional), trend (optional: "up"/"down"), description (optional)

### Table — data grid
{% table %}
{"headers": ["Ticker", "P/L", "ROE"], "rows": [["PETR4", "5.2x", "15%"], ["VALE3", "3.1x", "22%"]], "caption": "Valuation Comparison"}
{% /table %}
Props: headers (required), rows (required), caption (optional)

### Chart — data visualization
{% chart %}
{"type": "line", "title": "PETR4 Price History", "x": ["Jan", "Feb", "Mar"], "y": [28.5, 29.1, 30.2]}
{% /chart %}
Types: "bar", "line", "pie", "donut". Props: type (required), x (required), y (required), title (optional)

### Grid — multi-column layout
{% grid %}
{"cols": 3, "gap": "md", "items": [1, 2, 3]}
{% /grid %}
Use with stat cards for portfolio snapshots.

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

**Tag Rules:**
- {% stat %} for single metrics (P/L, ROE, DY, price, market cap)
- {% table %} for side-by-side comparisons
- {% chart %} for time series, trends, sector allocation
- {% grid %} + {% stat %} for dashboard layouts (3-col stat card grid)
- {% tabs %} for multi-view responses
- {% accordion %} for methodology, disclaimers, long explanations
- {% progress %} for allocation %, portfolio weight vs target
- {% card %} to group related content
- Wrap tag content in valid JSON, no extra text inside tags
- Mix prose and tags freely
""".replace("__DATE__", str(datetime.now().date()))


class Prometheus:
    def __init__(self):
        self.client = _get_client()

    @classmethod
    def buildSystemPrompt(
        cls,
        userId: int | None = None,
        db=None,
        sessionId: str | None = None,
    ) -> str:
        memoryBlock = ""
        if userId and db:
            # Intentional: the query is NOT passed here so the memory block is deterministic
            # per user (ranked by relevanceScore), keeping the system instruction stable so
            # the SDK's implicit prompt cache can hit. Query-specific retrieval remains
            # available via the search_memory tool.
            memories = PrometheusMemory.search(db, userId, "", limit=10)
            if memories:
                memoryBlock = "\n".join(f"- [{m['memoryType']}] {m['memoryKey']}: {m['memoryValue']}" for m in memories)

        episodeBlock = ""
        if sessionId and db:
            try:
                episodes = PrometheusCompactor().getEpisodes(db, sessionId)
                if episodes:
                    lines = [f"[{i + 1}] {ep.get('summary', '')}" for i, ep in enumerate(episodes[-5:])]
                    episodeBlock = "\n".join(lines)
            except Exception as e:
                logger.debug("Failed to load episodes for session %s: %s", sessionId, e)

        sections = [SYSTEM_PROMPT]
        if episodeBlock:
            sections.append(f"\n[HISTÓRICO DA SESSÃO]\n{episodeBlock}")
        if memoryBlock:
            sections.append(f"\n[MEMÓRIAS DO USUÁRIO]\n{memoryBlock}\n[/MEMÓRIAS DO USUÁRIO]")
        return "".join(sections)

    def makeChat(self, sessions, history, *, system_prompt=None, disable_automatic_function_calling=False):
        all_tools = list(sessions) + list(TOOL_REGISTRY.values())

        kwargs = dict(system_instruction=system_prompt, tools=all_tools, temperature=0.5, max_output_tokens=65536)
        if disable_automatic_function_calling:
            kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)

        return self.client.aio.chats.create(
            model="gemini-flash-lite-latest", history=history, config=types.GenerateContentConfig(**kwargs)
        )

    async def streamMessage(self, query=None, sessionId=None, db=None, user=None) -> AsyncIterator[dict]:
        if clientPool.clients is None:
            try:
                await clientPool.initialize()
                fieldRegistry.getFields()
            except Exception as e:
                logger.warning("Pool/registry startup failed: %s", e)

        try:
            session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
            if session and session.history:
                PrometheusCompactor().compact(db, str(sessionId))

            if session and user:
                spawnExtraction(user.get("userId"), str(sessionId), user.get("roles", []))
        except Exception:
            logger.debug("Pre-turn compaction skipped", exc_info=True)

        episodes = PrometheusCompactor().getEpisodes(db, str(sessionId))
        last_ep_time = episodes[-1].get("time") if episodes else None
        history = PrometheusChatManager.getHistory(db, str(sessionId), limit=50, since=last_ep_time)
        system_prompt = Prometheus.buildSystemPrompt(
            user.get("userId") if user else None,
            db,
            sessionId=str(sessionId),
        )

        # Persist the user turn up front so it survives mid-stream errors; the assistant
        # text is saved in the finally block below.
        PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))

        mcpClients, sessions = await clientPool.getClients()
        chat = self.makeChat(sessions, history, system_prompt=system_prompt, disable_automatic_function_calling=True)
        stream = await chat.send_message_stream(query)

        fullText = ""

        try:
            turn = 0
            while turn < MAX_TURNS:
                chunks_text = ""
                function_calls: list = []
                async for chunk in stream:
                    if hasattr(chunk, "text") and chunk.text:
                        chunks_text += chunk.text
                        fullText += chunk.text
                        yield {"type": "text", "text": chunk.text}
                    if hasattr(chunk, "function_calls") and chunk.function_calls:
                        fcs = chunk.function_calls
                        function_calls.extend(fcs.values() if isinstance(fcs, dict) else fcs)

                if not function_calls:
                    break

                turn_start = int(time.time() * 1000)
                tools_used = []
                responses = []

                sandbox_id = None
                for fc in function_calls:
                    tools_used.append(fc.name)
                    history.append(
                        {
                            "role": "loop_event",
                            "eventType": "tool_call",
                            "metadata": {"toolName": fc.name, "args": fc.args or {}, "turnNumber": turn},
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    yield {"type": "tool_call", "tool": fc.name, "args": fc.args or {}, "turn": turn}

                    if sessionId:
                        try:
                            PrometheusChatManager.saveLoopEvent(
                                db,
                                str(sessionId),
                                "tool_call",
                                {"toolName": fc.name, "args": fc.args or {}, "turn": turn},
                            )
                        except Exception as e:
                            logger.error(f"Failed to persist tool_call event: {e}")

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

                    result = await dispatchToolCall(fc, mcpClients, user=user, db=db, sandbox_id=sandbox_id)
                    history.append(
                        {
                            "role": "loop_event",
                            "eventType": "tool_result",
                            "metadata": {"toolName": fc.name, "result": result, "turnNumber": turn},
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    yield {"type": "tool_result", "tool": fc.name, "result": result, "turn": turn}
                    responses.append(types.Part.from_function_response(name=fc.name, response=result))

                    if sessionId:
                        try:
                            PrometheusChatManager.saveLoopEvent(
                                db,
                                str(sessionId),
                                "tool_result",
                                {"toolName": fc.name, "result": result, "turn": turn},
                            )
                        except Exception as e:
                            logger.error(f"Failed to persist tool_result event: {e}")

                history.append(
                    {
                        "role": "loop_event",
                        "eventType": "turn_end",
                        "metadata": {
                            "turnNumber": turn,
                            "durationMs": int(time.time() * 1000) - turn_start,
                            "toolsUsed": tools_used,
                        },
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                yield {
                    "type": "turn_end",
                    "turn": turn,
                    "durationMs": int(time.time() * 1000) - turn_start,
                    "toolsUsed": len(tools_used),
                }

                if sessionId:
                    try:
                        PrometheusChatManager.saveLoopEvent(
                            db,
                            str(sessionId),
                            "turn_end",
                            {
                                "turnNumber": turn,
                                "durationMs": int(time.time() * 1000) - turn_start,
                                "toolsUsed": tools_used,
                            },
                        )
                    except Exception as e:
                        logger.error(f"Failed to persist turn_end event: {e}")

                turn += 1
                stream = await chat.send_message_stream(responses)

            if turn >= MAX_TURNS:
                logger.warning("Prometheus hit max turns (%d) for session %s", MAX_TURNS, sessionId)
                yield {"type": "turn_limit", "maxTurns": MAX_TURNS}
        finally:
            # Persist whatever assistant text accumulated — full answer on success, partial
            # text on mid-stream error (the error then re-raises to the controller).
            if fullText:
                try:
                    PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", fullText)
                except Exception as e:
                    logger.error("Failed to persist assistant message: %s", e)
