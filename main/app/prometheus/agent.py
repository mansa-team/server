import logging
from config import Config

import json
from datetime import datetime, timedelta

from google import genai
from google.genai import types
from fastmcp import Client

from main.app.prometheus.chat import PrometheusChatManager

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

    async def sendMessage(
        self,
        query: str | None = None,
        sessionId: str | None = None,
        db=None
    ):
        logger.info(f"Query: {query}")

        history = PrometheusChatManager.getHistory(db, sessionId, limit=50)

        stocks = Client(f"http://{Config.STOCKS_API["HOST"]}:{Config.STOCKS_API["PORT"]}/stocks/mcp")
        async with stocks:
            chat = self.client.aio.chats.create(
                model="gemini-flash-lite-latest",
                history=history,
                config=types.GenerateContentConfig(
                    tools=[stocks.session],
                    temperature=0.5,
                ),
            )
            response = await chat.send_message(query)

        PrometheusChatManager.saveMessage(db, sessionId, "user", query)
        PrometheusChatManager.saveMessage(db, sessionId, "assistant", response.text)

        return response.text