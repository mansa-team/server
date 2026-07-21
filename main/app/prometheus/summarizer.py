import json
import uuid
import logging
from datetime import datetime, timezone

from google import genai
from google.genai import types

from sqlalchemy.orm import Session as DBSession

from config import Config
from main.models import PrometheusSession

logger = logging.getLogger(__name__)

_tokenizer = None


def _getTokenizer():
    global _tokenizer
    if _tokenizer is None:
        try:
            _tokenizer = genai.LocalTokenizer(model_name="gemini-flash-lite-latest")
            logger.info("Loaded Gemini local tokenizer")
        except Exception as e:
            logger.warning(f"Failed to load local tokenizer, using fallback: {e}")
            _tokenizer = None
    return _tokenizer


def countTokens(text: str) -> int:
    if not text:
        return 0
    tok = _getTokenizer()
    if tok is not None:
        try:
            result = tok.count_tokens(text)
            return result.total_tokens
        except Exception:
            pass
    # ponytail: fallback estimate, //3 is conservative for PT+EN mix
    return len(text) // 3


def smartTruncate(text: str, max_len: int = 500) -> str:
    if len(text) <= max_len:
        return text
    suffix = "..."
    cut = text[: max_len - len(suffix)].rsplit(" ", 1)[0]

    if "{%" in cut and cut.count("{%") > cut.count("%}"):
        cut = cut.rsplit("{%", 1)[0]
    return cut.strip() + suffix


SYSTEM_INSTRUCTION = """
You are a conversation summarizer. Compress the provided messages into a concise episode summary.

Rules:
- Be factual and objective — no opinions or interpretations
- Capture topic progression and key decisions made
- List concrete entities mentioned (tools, libraries, people, projects)
- Keep the summary to 2-3 sentences maximum
- Only include decisions that were actually made, not just discussed
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-3 sentence overview of what was discussed"},
        "keyDecisions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Actual decisions made during the conversation",
        },
        "entities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tools, libraries, people, or projects mentioned",
        },
    },
    "required": ["summary", "keyDecisions", "entities"],
}

MERGE_INSTRUCTION = """
You are merging conversation episode summaries into a single condensed summary.

Rules:
- Preserve ALL keyDecisions from all episodes (deduplicate)
- Preserve ALL entities mentioned (deduplicate)
- The summary should be a single paragraph covering the full arc
- Do not add information not present in the original episodes
- Keep the merged summary under 300 words
"""

MERGE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "keyDecisions": {"type": "array", "items": {"type": "string"}},
        "entities": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "keyDecisions", "entities"],
}


EPISODE_TOKEN_BUDGET = 8000
EPISODE_CAP = 12


class PrometheusSummarizer:
    def shouldSummarize(self, history: list) -> bool:
        if not history:
            return False
        total = sum(countTokens(m.get("content", "")) for m in history)
        return total >= EPISODE_TOKEN_BUDGET

    def getSummarizableChunk(self, history: list, episodes: list) -> list[dict]:
        if not episodes:
            return history

        lastEpTime = episodes[-1].get("time")
        if not lastEpTime:
            return history

        chunk = [m for m in history if m.get("timestamp", "") > lastEpTime]
        return chunk if chunk else history[-10:]

    def consolidate(self, episodes: list[dict]) -> list[dict]:
        if len(episodes) <= EPISODE_CAP:
            return episodes

        recent = episodes[-10:]
        old = episodes[:-10]

        if len(old) < 3:
            return episodes

        merged = self._mergeEpisodes(old)
        return [merged] + recent

    def _mergeEpisodes(self, episodes: list[dict]) -> dict:
        episode_texts = []
        all_decisions = []
        all_entities = []

        for ep in episodes:
            episode_texts.append(
                f"Episode {ep.get('id', '?')} ({ep.get('time', '?')})\n"
                f"Summary: {ep.get('summary', '')}\n"
                f"Decisions: {ep.get('keyDecisions', [])}\n"
                f"Entities: {ep.get('entities', [])}"
            )
            all_decisions.extend(ep.get("keyDecisions", []))
            all_entities.extend(ep.get("entities", []))

        contents = "\n\n".join(episode_texts)

        try:
            client = genai.Client(api_key=Config.PROMETHEUS["GEMINI_API.KEY"])
            resp = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=MERGE_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=MERGE_SCHEMA,
                    max_output_tokens=512,
                    temperature=0.0,
                ),
            )
            merged: dict = resp.parsed  # type: ignore[assignment]
        except Exception as e:
            logger.warning(f"Episode merge failed, using fallback: {e}")
            merged = {
                "summary": " | ".join(ep.get("summary", "") for ep in episodes),
                "keyDecisions": list(dict.fromkeys(all_decisions)),
                "entities": list(dict.fromkeys(all_entities)),
            }

        return {
            "id": f"ep_{uuid.uuid4().hex[:8]}",
            "time": datetime.now(timezone.utc).isoformat(),
            "summary": merged.get("summary", ""),
            "keyDecisions": merged.get("keyDecisions", []),
            "entities": merged.get("entities", []),
        }

    def summarize(self, db: DBSession, sessionId: str) -> dict | None:
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

        if not session or not session.history:
            return None

        chunk = self.getSummarizableChunk(session.history, self.getEpisodes(db, sessionId))  # type: ignore[arg-type]
        if not self.shouldSummarize(chunk):
            return None

        messages = "\n".join(
            f"{m.get('role', '?')}: {smartTruncate(m.get('content', ''), 500)}" for m in chunk if m.get("content")
        )

        try:
            client = genai.Client(api_key=Config.PROMETHEUS["GEMINI_API.KEY"])
            resp = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    max_output_tokens=256,
                    temperature=0.0,
                ),
            )
            episode: dict = resp.parsed  # type: ignore[assignment]
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return None

        obj = {
            "id": f"ep_{uuid.uuid4().hex[:8]}",
            "time": datetime.now(timezone.utc).isoformat(),
            "summary": episode.get("summary", ""),
            "keyDecisions": episode.get("keyDecisions", []),
            "entities": episode.get("entities", []),
        }

        existing = self.getEpisodes(db, sessionId)
        existing.append(obj)

        if len(existing) > EPISODE_CAP:
            existing = self.consolidate(existing)

        session.summary = json.dumps(existing)  # type: ignore[assignment]
        db.commit()

        return obj

    def getEpisodes(self, db: DBSession, sessionId: str) -> list[dict]:
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
        if not session or not session.summary:
            return []
        try:
            summary: str = session.summary  # type: ignore[assignment]
            episodes = json.loads(summary)
            return episodes if isinstance(episodes, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
