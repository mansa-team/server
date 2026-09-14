"""Tests for main/utils/logging_config.py — covers DiscordHandler branches."""

import logging
from unittest.mock import patch, MagicMock
import pytest


class TestDiscordHandlerEmit:
    @pytest.fixture(autouse=True)
    def _isolate_root_handlers(self):
        # Import-time setupDiscordHandler() installs a real QueueHandler on
        # the root logger + a live QueueListener thread. While Config is
        # mocked, any ERROR log anywhere would ride that path into the
        # globally-mocked requests.post and inflate call_count (2 == 1
        # flakes). Detach root handlers + drain the queue per test.
        import queue

        import main.utils.logging_config as lc

        root = logging.getLogger()
        saved = list(root.handlers)
        root.handlers.clear()
        try:
            while True:
                lc.discordQueue.get_nowait()
        except queue.Empty:
            pass
        try:
            yield
        finally:
            root.handlers[:] = saved

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

    @patch("main.utils.logging_config.requests.post")
    @patch("main.utils.logging_config.Config")
    def test_message_queued_on_error(self, mockConfig, mockPost):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self.make_handler()
        record = self.make_record(level=logging.ERROR, msg="something broke")
        handler.emit(record)
        assert mockPost.call_count == 1

    @patch("main.utils.logging_config.requests.post")
    @patch("main.utils.logging_config.Config")
    def test_message_truncation(self, mockConfig, mockPost):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self.make_handler()
        long_msg = "x" * 3000
        record = self.make_record(level=logging.ERROR, msg=long_msg)
        handler.emit(record)
        assert mockPost.call_count == 1
        content = mockPost.call_args.kwargs["json"]["content"]
        assert len(content) <= 2000

    @patch("main.utils.logging_config.requests.post")
    @patch("main.utils.logging_config.Config")
    def test_emit_does_not_raise(self, mockConfig, mockPost):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self.make_handler()
        record = self.make_record(level=logging.ERROR, msg="test")
        # Should not raise
        handler.emit(record)

    @patch("main.utils.logging_config.requests.post")
    @patch("main.utils.logging_config.Config")
    def test_with_exception_info(self, mockConfig, mockPost):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        handler = self.make_handler()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = self.make_record(level=logging.ERROR, msg="failed", exc_info=exc_info)
        handler.emit(record)
        assert mockPost.call_count == 1
        content = mockPost.call_args.kwargs["json"]["content"]
        assert "ValueError" in content


class TestSetupLogging:
    @patch("main.utils.logging_config.QueueListener")
    @patch("main.utils.logging_config.Config")
    def test_setup_discord_handler_enabled(self, mockConfig, mockListenerCls):
        mockConfig.DISCORD.ENABLED = True
        mockConfig.DISCORD.WEBHOOK_URL = "https://hook.test/123"
        from main.utils.logging_config import setupDiscordHandler

        root = logging.getLogger()
        before = list(root.handlers)
        try:
            # Should add handler (listener mocked: no real thread starts)
            setupDiscordHandler()
            mockListenerCls.assert_called_once()
            mockListenerCls.return_value.start.assert_called_once()
        finally:
            for h in list(root.handlers):
                if h not in before:
                    root.removeHandler(h)
                    try:
                        h.close()
                    except Exception:
                        pass
            try:
                mockListenerCls.return_value.stop()
            except Exception:
                pass

    @patch("main.utils.logging_config.QueueListener")
    @patch("main.utils.logging_config.Config")
    def test_setup_discord_handler_disabled(self, mockConfig, mockListenerCls):
        mockConfig.DISCORD.ENABLED = False
        from main.utils.logging_config import setupDiscordHandler

        setupDiscordHandler()
        mockListenerCls.assert_not_called()
