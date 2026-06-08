"""Tests for main/utils/logging_config.py — covers DiscordHandler branches."""

import logging
from unittest.mock import patch, MagicMock
import pytest


class TestDiscordHandlerEmit:
    def _make_handler(self):
        from main.utils.logging_config import DiscordHandler

        return DiscordHandler()

    def _make_record(self, level=logging.ERROR, msg="test error", exc_info=None):
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
        handler = self._make_handler()
        record = self._make_record()
        # Should not raise, early return
        handler.emit(record)

    @patch("main.utils.logging_config.Config")
    def test_discord_no_webhook(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = None
        handler = self._make_handler()
        record = self._make_record()
        handler.emit(record)

    @patch("main.utils.logging_config.Config")
    def test_level_below_error(self, mockConfig):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self._make_handler()
        record = self._make_record(level=logging.WARNING)
        handler.emit(record)

    @patch("main.utils.logging_config.discordExecutor")
    @patch("main.utils.logging_config.Config")
    def test_submit_called_on_error(self, mockConfig, mockExecutor):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self._make_handler()
        record = self._make_record(level=logging.ERROR, msg="something broke")
        handler.emit(record)
        mockExecutor.submit.assert_called_once()

    @patch("main.utils.logging_config.discordExecutor")
    @patch("main.utils.logging_config.Config")
    def test_message_truncation(self, mockConfig, mockExecutor):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self._make_handler()
        long_msg = "x" * 3000
        record = self._make_record(level=logging.ERROR, msg=long_msg)
        handler.emit(record)
        # Verify submit was called (truncation happens before submit)
        mockExecutor.submit.assert_called_once()
        call_args = mockExecutor.submit.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][2]
        assert len(payload["content"]) <= 2000

    @patch("main.utils.logging_config.discordExecutor")
    @patch("main.utils.logging_config.Config")
    def test_exception_in_submit(self, mockConfig, mockExecutor):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        mockExecutor.submit.side_effect = RuntimeError("executor full")
        handler = self._make_handler()
        record = self._make_record(level=logging.ERROR, msg="test")
        # Should not raise
        handler.emit(record)

    @patch("main.utils.logging_config.discordExecutor")
    @patch("main.utils.logging_config.Config")
    def test_with_exception_info(self, mockConfig, mockExecutor):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self._make_handler()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = self._make_record(level=logging.ERROR, msg="failed", exc_info=exc_info)
        handler.emit(record)
        mockExecutor.submit.assert_called_once()


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
