from config import Config
import re
import json
import uuid
import time
import logging
from datetime import datetime
from urllib.request import urlopen, Request

from google import genai
from sqlalchemy.orm import Session as DBSession

from main.models import PrometheusSession

logger = logging.getLogger(__name__)

EPISODE_TOKEN_BUDGET = 8000
EPISODE_CAP = 12

TICKER_RE = re.compile(r"\b([A-Z]{4}[0-9])\b")

DECISION_KEYWORDS = re.compile(
    r"(?:prefiro|prefere|quero|gostaria|sempre|nunca|quando|"
    r"não use|use ao invés|troque|prefira|defina|configure|"
    r"prefer|always|never|want|don't use|use instead|define|configure)",
    re.IGNORECASE,
)

SNAPSHOT_VALUE_RE = re.compile(r"([\w\s/.,]+?):\s*([\-]?[\d.,]+)\s*(x|%|pts|R\$)?")

tokenizer = None


def getTokenizer():
    global tokenizer
    if tokenizer is None:
        try:
            tokenizer = genai.LocalTokenizer(model_name="gemini-flash-lite-latest")
            logger.info("Loaded Gemini local tokenizer")
        except Exception as e:
            logger.warning("Failed to load local tokenizer, using fallback: %s", e)
            tokenizer = None
    return tokenizer


def countTokens(text: str) -> int:
    if not text:
        return 0
    tok = getTokenizer()
    if tok is not None:
        try:
            result = tok.count_tokens(text)
            return result.total_tokens
        except Exception:
            pass
    return len(text) // 3


FALLBACK_FIELDS = [
    "P/L",
    "P/VP",
    "P/EBIT",
    "P/ATIVO",
    "EV/EBIT",
    "PSR",
    "ROE",
    "ROA",
    "ROIC",
    "DY",
    "MARGEM BRUTA",
    "MARGEM EBIT",
    "MARG. LIQUIDA",
    "MARGEM EBITDA",
    "LPA",
    "VPA",
    "PEG Ratio",
    "SGR",
    "INVESTING SCORE",
    "LIQ. CORRENTE",
    "DIV. LIQ. / PATRI.",
    "PASSIVO / ATIVOS",
    "GIRO ATIVOS",
    "PRECO DE GRAHAM",
    "PRECO DE BAZIN",
    "TAG ALONG",
]


class FieldRegistry:
    fields: list[str] | None = None
    fetchedAt: float = 0
    ttl: float = 3600

    def buildUrl(self) -> str:
        host = Config.STOCKS_API.HOST
        port = Config.STOCKS_API.PORT
        return f"http://{host}:{port}/stocks/fields"

    def fetchFields(self) -> list[str]:
        try:
            url = self.buildUrl()
            req = Request(url, headers={"X-MCP": "true"})
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            fields: list[str] = []
            historical = data.get("historical", {})
            if isinstance(historical, dict):
                fields.extend(historical.keys())
            fundamental = data.get("fundamental", [])
            if isinstance(fundamental, list):
                fields.extend(fundamental)

            logger.info("FieldRegistry: fetched %d fields from Stocks API", len(fields))
            return list(dict.fromkeys(fields))
        except Exception as e:
            logger.warning("FieldRegistry: failed to fetch fields, using fallback: %s", e)
            return list(FALLBACK_FIELDS)

    def getFields(self) -> list[str]:
        now = time.time()
        if self.fields is None or (now - self.fetchedAt) > self.ttl:
            self.fields = self.fetchFields()
            self.fetchedAt = now
        return self.fields

    def buildMetricRegex(self) -> re.Pattern:
        fields = self.getFields()
        escaped = [re.escape(f) for f in fields if len(f) > 1]
        escaped.sort(key=len, reverse=True)
        pattern = r"\b(" + "|".join(escaped) + r")\b"
        return re.compile(pattern)

    def getMetricRegex(self) -> re.Pattern:
        if not hasattr(self, "metricRegex") or self.fields is None:
            self.metricRegex = self.buildMetricRegex()
        return self.metricRegex

    def invalidate(self):
        self.fields = None
        self.fetchedAt = 0
        if hasattr(self, "metricRegex"):
            del self.metricRegex

    def warmup(self):
        self.fetchFields()
        self.fetchedAt = time.time()


fieldRegistry = FieldRegistry()


def charCount(text: str) -> int:
    return countTokens(text)


def extractTickers(text: str) -> list[str]:
    return list(dict.fromkeys(TICKER_RE.findall(text)))


def extractMetrics(text: str, registry: FieldRegistry | None = None) -> list[str]:
    if registry is not None:
        regex = registry.getMetricRegex()
    else:
        escaped = [re.escape(f) for f in FALLBACK_FIELDS if len(f) > 1]
        escaped.sort(key=len, reverse=True)
        regex = re.compile(r"\b(" + "|".join(escaped) + r")\b")
    return list(dict.fromkeys(regex.findall(text)))


def extractDecisions(userMessages: list[dict]) -> list[str]:
    decisions = []
    for msg in userMessages:
        content = msg.get("content", "")
        if not content:
            continue
        sentences = re.split(r"[.!?\n]", content)
        for sent in sentences:
            sent = sent.strip()
            if sent and DECISION_KEYWORDS.search(sent):
                decisions.append(sent[:200])
    return list(dict.fromkeys(decisions))[:10]


def extractSnapshots(toolResults: list[dict]) -> list[str]:
    snapshots = []
    for tr in toolResults:
        content = str(tr.get("content", ""))
        for match in SNAPSHOT_VALUE_RE.finditer(content):
            label = match.group(1).strip()
            value = match.group(2)
            unit = match.group(3) or ""
            if any(kw in label.upper() for kw in ["P/L", "ROE", "DY", "PRECO", "LPA", "VPA"]):
                snapshots.append(f"{label}: {value}{unit}")
    return list(dict.fromkeys(snapshots))[:10]


def extractToolCalls(loopEvents: list[dict]) -> list[str]:
    calls = []
    for ev in loopEvents:
        if ev.get("eventType") != "tool_call":
            continue
        meta = ev.get("metadata", {})
        toolName = meta.get("toolName", "")
        args = meta.get("args", {})
        ticker = args.get("search", "") or args.get("ticker", "")
        if ticker:
            calls.append(f"{toolName}({ticker})")
        else:
            calls.append(toolName)
    return list(dict.fromkeys(calls))[:15]


def buildSummary(
    tickers: list[str],
    tools: list[str],
    decisions: list[str],
    metrics: list[str],
    snapshots: list[str],
) -> str:
    parts = []
    if tickers:
        parts.append(f"Tickers analyzed: {', '.join(tickers[:5])}")
    if tools:
        parts.append(f"Tools used: {', '.join(tools[:5])}")
    if metrics:
        parts.append(f"Metrics considered: {', '.join(metrics[:5])}")
    if snapshots:
        parts.append(f"Key values: {'; '.join(snapshots[:3])}")
    if decisions:
        parts.append(f"User decisions: {'; '.join(decisions[:3])}")
    return " | ".join(parts) if parts else "Session with no extractable data."


class PrometheusCompactor:
    def __init__(self):
        self.registry = fieldRegistry

    def shouldCompact(self, history: list) -> bool:
        if not history:
            return False
        total = sum(charCount(m.get("content", "")) for m in history)
        return total >= EPISODE_TOKEN_BUDGET

    def getCompactableChunk(self, history: list, episodes: list) -> list[dict]:
        if not episodes:
            return history
        lastEpTime = episodes[-1].get("time")
        if not lastEpTime:
            return history
        chunk = [m for m in history if m.get("timestamp", "") > lastEpTime]
        return chunk if chunk else history[-10:]

    def extractEpisode(self, chunk: list[dict]) -> dict:
        userMessages = [m for m in chunk if m.get("role") == "user"]
        loopEvents = [m for m in chunk if m.get("role") == "loop_event"]
        toolResults = [m for m in loopEvents if m.get("eventType") == "tool_result"]

        allText = " ".join(m.get("content", "") for m in chunk if m.get("content"))

        tickers = extractTickers(allText)
        metrics = extractMetrics(allText, registry=self.registry)
        decisions = extractDecisions(userMessages)
        snapshots = extractSnapshots(toolResults)
        tools = extractToolCalls(loopEvents)

        summary = buildSummary(tickers, tools, decisions, metrics, snapshots)
        entities = list(dict.fromkeys(tickers + metrics))

        return {
            "summary": summary,
            "keyDecisions": decisions,
            "entities": entities,
        }

    def consolidate(self, episodes: list[dict]) -> list[dict]:
        if len(episodes) <= EPISODE_CAP:
            return episodes

        recent = episodes[-10:]
        old = episodes[:-10]

        if len(old) < 3:
            return episodes

        mergedSummary = " | ".join(ep.get("summary", "") for ep in old)
        allDecisions = []
        allEntities = []
        for ep in old:
            allDecisions.extend(ep.get("keyDecisions", []))
            allEntities.extend(ep.get("entities", []))

        merged = {
            "id": f"ep_{uuid.uuid4().hex[:8]}",
            "time": datetime.now().isoformat(),
            "summary": mergedSummary[:1000],
            "keyDecisions": list(dict.fromkeys(allDecisions)),
            "entities": list(dict.fromkeys(allEntities)),
        }

        return [merged] + recent

    def compact(self, db: DBSession, sessionId: str) -> dict | None:
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

        if not session or not session.history:
            return None

        episodes = self.getEpisodes(db, sessionId)
        chunk = self.getCompactableChunk(list(session.history) if session.history else [], episodes)

        if not self.shouldCompact(chunk):
            return None

        episodeData = self.extractEpisode(chunk)
        episode = {
            "id": f"ep_{uuid.uuid4().hex[:8]}",
            "time": datetime.now().isoformat(),
            "summary": episodeData["summary"],
            "keyDecisions": episodeData["keyDecisions"],
            "entities": episodeData["entities"],
        }

        existing = self.getEpisodes(db, sessionId)
        existing.append(episode)

        if len(existing) > EPISODE_CAP:
            existing = self.consolidate(existing)

        session.summary = json.dumps(existing)  # type: ignore[assignment]
        db.commit()

        logger.info(
            "Compacted %d messages into episode %s (decisions=%d, entities=%d)",
            len(chunk),
            episode["id"],
            len(episode["keyDecisions"]),
            len(episode["entities"]),
        )
        return episode

    def getEpisodes(self, db: DBSession, sessionId: str) -> list[dict]:
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
        if not session or not session.summary:
            return []
        try:
            episodes = json.loads(str(session.summary))
            return episodes if isinstance(episodes, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
