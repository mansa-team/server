"""Tests for main/utils/logging_config.py — covers DiscordHandler branches."""

import logging
from unittest.mock import patch, MagicMock
import pytest


class TestDiscordHandlerEmit:
    def make_handler(self):
        from main.utils.logging_config import DiscordHandler

        return DiscordHandler()

    def make_record(self, level=logging.ERROR, msg="test error", exc_info=None):
        record = logging.LogRecord(
            name="test.module",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=exc_info,
        )
        return record

    @patch("main.utils.logging_config.Config")
    def test_discord_disabled(self, mockConfig):
        mockConfig.DISCORD.ENABLED = False
        handler = self.make_handler()
        record = self.make_record()
        # Should not raise, early return
        handler.emit(record)

    @patch("main.utils.logging_config.Config")
    def test_discord_no_webhook(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = None
        handler = self.make_handler()
        record = self.make_record()
        handler.emit(record)

    @patch("main.utils.logging_config.Config")
    def test_level_below_error(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self.make_handler()
        record = self.make_record(level=logging.WARNING)
        handler.emit(record)

    @patch("main.utils.logging_config.Config")
    def test_message_queued_on_error(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        from main.utils.logging_config import queue, lock

        handler = self.make_handler()
        with lock:
            queue.clear()
        record = self.make_record(level=logging.ERROR, msg="something broke")
        handler.emit(record)
        with lock:
            assert len(queue) == 1

    @patch("main.utils.logging_config.Config")
    def test_message_truncation(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        from main.utils.logging_config import queue, lock

        handler = self.make_handler()
        with lock:
            queue.clear()
        long_msg = "x" * 3000
        record = self.make_record(level=logging.ERROR, msg=long_msg)
        handler.emit(record)
        with lock:
            assert len(queue) == 1
            assert len(queue[0]) <= 2000

    @patch("main.utils.logging_config.Config")
    def test_emit_does_not_raise(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self.make_handler()
        record = self.make_record(level=logging.ERROR, msg="test")
        # Should not raise
        handler.emit(record)

    @patch("main.utils.logging_config.Config")
    def test_with_exception_info(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        from main.utils.logging_config import queue, lock

        handler = self.make_handler()
        with lock:
            queue.clear()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = self.make_record(level=logging.ERROR, msg="failed", exc_info=exc_info)
        handler.emit(record)
        with lock:
            assert len(queue) == 1
            assert "ValueError" in queue[0]


class TestSetupLogging:
    @patch("main.utils.logging_config.Config")
    def test_setup_discord_handler_enabled(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        from main.utils.logging_config import setupDiscordHandler

        # Should add handler
        setupDiscordHandler()

    @patch("main.utils.logging_config.Config")
    def test_setup_discord_handler_disabled(self, mockConfig):
        mockConfig.DISCORD.ENABLED = False
        from main.utils.logging_config import setupDiscordHandler

        setupDiscordHandler()
