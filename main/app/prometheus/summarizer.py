"""Summarize conversation history into episode summaries."""

import json
import uuid
import logging
from datetime import datetime, timezone

from google import genai
from google.genai import types

from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm.attributes import flag_modified

from config import Config
from main.models import PrometheusSession

logger = logging.getLogger(__name__)


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


class PrometheusSummarizer:
    def summarize(self, db: DBSession, sessionId: str) -> dict | None:
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

        if not session or not session.history or len(session.history) < 20:
            return None

        history: list[dict] = session.history  # type: ignore[assignment]

        messages = "\n".join(
            f"{m.get('role', '?')}: {smartTruncate(m.get('content', ''), 500)}"
            for m in history[-50:]
            if m.get("content")
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

        session.summary = json.dumps(existing[-20:])  # type: ignore[assignment]
        session.history = session.history[-20:]  # type: ignore[assignment]
        flag_modified(session, "history")

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
