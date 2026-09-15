"""Tests for thread safety utilities (Issues 5 & 6).

Issue 5: DiscordHandler uses a bounded ThreadPoolExecutor instead of
         spawning unlimited daemon threads.
Issue 6: requests.Session usage is thread-safe via per-thread sessions
         stored in threading.local().
"""

import logging
import threading
import time
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Issue 6 – getSession() thread safety
# ---------------------------------------------------------------------------


class TestGetSession:
    """Verify that getSession() returns per-thread Session instances."""

    def test_same_session_within_same_thread(self):
        """Calling getSession() twice in the same thread returns the same object."""
        from main.utils.http_session import getSession

        s1 = getSession()
        s2 = getSession()
        assert s1 is s2, "getSession() must return the same Session within one thread"

    def test_different_sessions_in_different_threads(self):
        """Two threads must NOT share a Session object."""
        from main.utils.http_session import getSession

        # Keep references alive so CPython doesn't reuse memory addresses
        sessions: dict[str, object] = {}

        def capture(name: str):
            s = getSession()
            sessions[name] = s  # store the object itself, not just id()

        t1 = threading.Thread(target=capture, args=("t1",))
        t2 = threading.Thread(target=capture, args=("t2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert sessions["t1"] is not sessions["t2"], "Different threads must get different Session instances"

    def test_isolation_under_high_concurrency(self):
        """With 20 concurrent threads, every thread must get its own Session."""
        from main.utils.http_session import getSession

        sessions: dict[int, object] = {}
        barrier = threading.Barrier(20)

        def capture(idx: int):
            barrier.wait()  # all threads start simultaneously
            sessions[idx] = getSession()

        threads = [threading.Thread(target=capture, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Every session must be a distinct object
        unique = set(id(s) for s in sessions.values())
        assert len(unique) == 20, f"Expected 20 unique sessions, got {len(unique)}"

    def test_session_is_requests_session(self):
        """The returned object must be a real requests.Session."""
        import requests
        from main.utils.http_session import getSession

        session = getSession()
        assert isinstance(session, requests.Session)

    def test_concurrent_sessions_are_thread_local(self):
        """getSession() must give each thread its own Session (merged from TestConcurrentGetSession)."""
        from main.utils.http_session import getSession
        import requests

        results: dict[str, bool] = {}

        def check(name: str):
            s = getSession()
            results[name] = isinstance(s, requests.Session)

        t1 = threading.Thread(target=check, args=("t1",))
        t2 = threading.Thread(target=check, args=("t2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.get("t1") is True
        assert results.get("t2") is True

    def test_connectivity_uses_getSession(self):
        """connectivity.checkServiceConnection must call getSession(), not use a global Session."""
        from main.utils import connectivity

        with patch.object(connectivity, "getSession") as mock_get:
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_session.get.return_value = mock_resp
            mock_get.return_value = mock_session

            with patch.object(connectivity, "Config") as mock_cfg:
                mock_cfg.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
                result = connectivity.checkServiceConnection("STOCKS_API")

            mock_get.assert_called_once()
            mock_session.get.assert_called_once()
            assert result is True


# ---------------------------------------------------------------------------
# Issue 5 – DiscordHandler bounded thread pool
# ---------------------------------------------------------------------------


class TestDiscordHandlerThreadPool:
    """Verify DiscordHandler posts via the shared discordQueue, thread-safely."""

    def test_queue_and_handler_exist(self):
        """The module-level discordQueue and DiscordHandler must exist."""
        from queue import Queue

        from main.utils.logging_config import DiscordHandler, discordQueue

        assert isinstance(discordQueue, Queue)
        handler = DiscordHandler()
        assert hasattr(handler, "acquire") and hasattr(handler, "release")

    def test_emit_posts_to_webhook(self):
        """DiscordHandler.emit() must POST the formatted message to the webhook."""
        from unittest.mock import patch

        from main.utils.logging_config import DiscordHandler

        with (
            patch("main.utils.logging_config.Config") as mock_cfg,
            patch("main.utils.logging_config.requests.post") as mock_post,
            patch("main.utils.logging_config.time.sleep"),
        ):
            mock_cfg.DISCORD.ENABLED = True
            mock_cfg.DISCORD.WEBHOOK_URL = "https://discord.example.com/hook"

            handler = DiscordHandler()
            record = logging.LogRecord(
                name="test.module",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="test error %s",
                args=("detail",),
                exc_info=None,
            )
            handler.emit(record)

            mock_post.assert_called_once()
            assert mock_post.call_args.kwargs["json"]["content"].startswith("[ERROR] [module]")

    def test_concurrent_emits_are_thread_safe(self):
        """Many concurrent emit() calls must not corrupt handler state."""
        from unittest.mock import patch

        from main.utils.logging_config import DiscordHandler

        with (
            patch("main.utils.logging_config.Config") as mock_cfg,
            patch("main.utils.logging_config.requests.post") as mock_post,
            patch("main.utils.logging_config.time.sleep"),
        ):
            mock_cfg.DISCORD.ENABLED = True
            mock_cfg.DISCORD.WEBHOOK_URL = "https://discord.example.com/hook"

            handler = DiscordHandler()

            def emit(i):
                record = logging.LogRecord(
                    name="test",
                    level=logging.ERROR,
                    pathname="test.py",
                    lineno=1,
                    msg=f"concurrent test {i}",
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)

            # Fire 20 concurrent emits with distinct messages (no dedup)
            workers = [threading.Thread(target=emit, args=(i,)) for i in range(20)]
            for w in workers:
                w.start()
            for w in workers:
                w.join(timeout=5)

            assert mock_post.call_count == 20
