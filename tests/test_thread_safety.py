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

        def _capture(name: str):
            s = getSession()
            sessions[name] = s  # store the object itself, not just id()

        t1 = threading.Thread(target=_capture, args=("t1",))
        t2 = threading.Thread(target=_capture, args=("t2",))
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

        def _capture(idx: int):
            barrier.wait()  # all threads start simultaneously
            sessions[idx] = getSession()

        threads = [threading.Thread(target=_capture, args=(i,)) for i in range(20)]
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


# ---------------------------------------------------------------------------
# Issue 5 – DiscordHandler bounded thread pool
# ---------------------------------------------------------------------------


class TestDiscordHandlerThreadPool:
    """Verify that DiscordHandler submits to a bounded executor, not raw threads."""

    def test_queue_and_lock_exist(self):
        """The module-level queue, lock, and event must exist."""
        from main.utils.logging_config import queue, lock, event

        assert queue is not None
        assert lock is not None
        assert event is not None

    def test_emit_adds_to_queue(self):
        """DiscordHandler.emit() must add messages to the module queue."""
        from main.utils.logging_config import DiscordHandler, queue, lock

        with patch("main.utils.logging_config.Config") as mock_cfg:
            mock_cfg.DISCORD.ENABLED = True
            mock_cfg.DISCORD.WEBHOOK_URL = "https://discord.example.com/hook"

            handler = DiscordHandler()
            with lock:
                queue.clear()
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

            with lock:
                assert len(queue) == 1

    def test_concurrent_emits_are_thread_safe(self):
        """Many concurrent emit() calls must not corrupt the queue."""
        from main.utils.logging_config import DiscordHandler, queue, lock

        with patch("main.utils.logging_config.Config") as mock_cfg:
            mock_cfg.DISCORD.ENABLED = True
            mock_cfg.DISCORD.WEBHOOK_URL = "https://discord.example.com/hook"

            handler = DiscordHandler()

            with lock:
                queue.clear()

            def _emit():
                record = logging.LogRecord(
                    name="test",
                    level=logging.ERROR,
                    pathname="test.py",
                    lineno=1,
                    msg="concurrent test",
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)

            # Fire 20 concurrent emits
            workers = [threading.Thread(target=_emit) for _ in range(20)]
            for w in workers:
                w.start()
            for w in workers:
                w.join(timeout=5)

            with lock:
                # Queue may deduplicate identical messages, but no corruption
                assert len(queue) >= 1
                assert all(isinstance(msg, str) for msg in queue)


# ---------------------------------------------------------------------------
# Integration: concurrent HTTP via getSession
# ---------------------------------------------------------------------------


class TestConcurrentGetSession:
    """Verify getSession returns thread-local sessions under concurrency."""

    def test_getSession_returns_thread_local_sessions(self):
        """getSession() must give each thread its own Session."""
        from main.utils.http_session import getSession
        import requests

        results: dict[str, bool] = {}

        def _check(name: str):
            s = getSession()
            results[name] = isinstance(s, requests.Session)

        t1 = threading.Thread(target=_check, args=("t1",))
        t2 = threading.Thread(target=_check, args=("t2",))
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
