import json
import threading
from datetime import datetime
from typing import Optional
import requests

from config import Config

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

class DiscordWebhook:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, tag: str, message: str, level: str = "info"):
        if not self.webhook_url:
            return

        try:
            color = 16711680 if level == "error" else 5805790 if level == "warning" else 31019

            payload = {
                "embeds": [
                    {
                        "title": f"[{tag.upper()}] {level.upper()}",
                        "description": message[:2000],
                        "color": color,
                        "footer": {"text": "Mansa Server"},
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ]
            }

            threading.Thread(target=self._send_async, args=(payload,), daemon=True).start()
        except Exception:
            pass

    def _send_async(self, payload: dict):
        try:
            requests.post(self.webhook_url, json=payload, timeout=5)
        except Exception:
            pass

def _get_webhook() -> Optional[DiscordWebhook]:
    if not Config.DISCORD.ENABLED:
        return None
    url = Config.DISCORD.WEBHOOK_URL
    if not url:
        return None
    return DiscordWebhook(url)

def log(tag: str, message: str):
    if Config.DEBUG_MODE:
        print(f"[{tag.upper()}] {message}", flush=True)

    if Config.DISCORD.ENABLED:
        webhook = _get_webhook()
        if webhook: webhook.send(tag, message, level="info")

def log_error(tag: str, message: str, exc: Optional[Exception] = None):
    full_message = f"{message}"
    if exc:
        full_message += f"\n```\n{type(exc).__name__}: {str(exc)}\n```"

    if Config.DEBUG_MODE:
        print(f"[{tag.upper()}] ERROR: {full_message}", flush=True)

    if Config.DISCORD.ENABLED:
        webhook = _get_webhook()
        if webhook:
            webhook.send(tag, full_message, level="error")