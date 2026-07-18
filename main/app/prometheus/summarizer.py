"""Summarize conversation history into episode summaries."""

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

        messages = "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')[:500]}" for m in session.history[-50:] if m.get("content")
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
            episode = resp.parsed
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

        session.summary = json.dumps(existing[-20:])
        db.commit()

        return obj

    def getEpisodes(self, db: DBSession, sessionId: str) -> list[dict]:
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
        if not session or not session.summary:
            return []
        try:
            episodes = json.loads(session.summary)
            return episodes if isinstance(episodes, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
