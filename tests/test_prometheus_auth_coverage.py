"""
Tests to increase coverage for:
  - main/app/prometheus/generation.py
  - main/app/prometheus/chat.py
  - main/app/authentication/authentication.py
  - main/app/authentication/session.py
  - main/app/authentication/sso.py
"""

import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
from pytz import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# PrometheusGenerator (generation.py)
# ---------------------------------------------------------------------------


class TestPrometheusGeneratorInit:
    """Cover __init__ and updateDates (lines 22-37)."""

    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_init_creates_client_and_updates_dates_debug(self, mock_genai, mock_config):
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "test-key"}
        mock_config.DEBUG_MODE = True

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        mock_genai.Client.assert_called_once_with(api_key="test-key")
        assert gen.currentDate == "23/03/2026"
        assert gen.currentISODate == "2026-03-23"
        assert gen.currentYear == 2026
        assert gen.lastYear == 2025

    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_init_creates_client_and_updates_dates_prod(self, mock_genai, mock_config):
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "test-key"}
        mock_config.DEBUG_MODE = False

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        assert gen.currentYear == datetime.now().year
        assert gen.lastYear == gen.currentYear - 1


class TestPrometheusGeneratorExecuteWorkflow:
    """Cover executeWorkflow (lines 39-363)."""

    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def _make_generator(self, mock_genai, mock_config, debug=True):
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "test-key"}
        mock_config.DEBUG_MODE = debug
        from main.app.prometheus.generation import PrometheusGenerator

        return PrometheusGenerator()

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_execute_workflow_basic_no_history(self, mock_genai, mock_config, mock_getSession):
        """Stage 1 + Stage 2 + Stage 3, no history, no sessionId."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        # Stage 1 response: single ticker request
        stage1_resp = MagicMock()
        stage1_resp.text = json.dumps(
            [
                {
                    "search": "PETR4",
                    "fields": "P/L",
                    "type": "fundamental",
                    "date_start": "2026-03-23",
                    "date_end": "2026-03-23",
                }
            ]
        )

        # Stage 3 response
        stage3_resp = MagicMock()
        stage3_resp.text = "Final analysis of PETR4"

        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        # HTTP response for stock data
        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 200
        mock_http_resp.json.return_value = {"data": [{"P/L": 8.5, "TICKER": "PETR4"}]}
        mock_getSession.return_value.get.return_value = mock_http_resp

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()

        result = gen.executeWorkflow("Qual o P/L de PETR4?")
        assert result == "Final analysis of PETR4"

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_execute_workflow_with_history(self, mock_genai, mock_config, mock_getSession):
        """Test history formatting (lines 48-49, 159-162)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = "[]"
        stage3_resp = MagicMock()
        stage3_resp.text = "No data found"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()

        history = [{"role": "user", "parts": [{"text": "hello"}]}] * 25  # More than 20
        result = gen.executeWorkflow("oi", history=history)
        assert result == "No data found"

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    @patch("main.app.prometheus.generation.PrometheusSession")
    def test_execute_workflow_with_session_summary(self, mock_session_model, mock_genai, mock_config, mock_getSession):
        """Stage 0: sessionId+db summary loading (lines 55-62)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = "[]"
        stage3_resp = MagicMock()
        stage3_resp.text = "Response"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        # Mock DB session
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.summary = "Previous discussion about PETR4"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        result = gen.executeWorkflow("oi", sessionId="sess-123", db=mock_db)
        assert result == "Response"

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    @patch("main.app.prometheus.generation.PrometheusSession")
    def test_execute_workflow_session_db_exception(self, mock_session_model, mock_genai, mock_config, mock_getSession):
        """Stage 0: exception loading session (line 62)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = "[]"
        stage3_resp = MagicMock()
        stage3_resp.text = "Response"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        result = gen.executeWorkflow("oi", sessionId="sess-123", db=mock_db)
        assert result == "Response"

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_execute_workflow_global_request_with_api_key(self, mock_genai, mock_config, mock_getSession):
        """Global request resolution with KEY_SYSTEM=True (lines 180-209)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "secret123", "KEY_SYSTEM": True, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        # Stage 1: global request (empty search, fundamental type)
        stage1_resp = MagicMock()
        stage1_resp.text = json.dumps(
            [
                {
                    "search": "",
                    "fields": "INVESTING SCORE",
                    "type": "fundamental",
                    "date_start": "2026-03-23",
                    "date_end": "2026-03-23",
                    "order_by": "INVESTING SCORE",
                    "limit": 10,
                }
            ]
        )
        stage3_resp = MagicMock()
        stage3_resp.text = "Global analysis"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        # Global tickers API response
        mock_global_resp = MagicMock()
        mock_global_resp.status_code = 200
        mock_global_resp.json.return_value = {"data": [{"TICKER": "PETR4"}, {"TICKER": "VALE3"}]}

        # Stock data response
        mock_stock_resp = MagicMock()
        mock_stock_resp.status_code = 200
        mock_stock_resp.json.return_value = {"data": [{"INVESTING SCORE": 9.0}]}

        mock_getSession.return_value.get.side_effect = [mock_global_resp, mock_stock_resp]

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        result = gen.executeWorkflow("Melhores ações")
        assert result == "Global analysis"

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_execute_workflow_global_request_api_error(self, mock_genai, mock_config, mock_getSession):
        """Global request API error (lines 208-209)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = json.dumps(
            [
                {
                    "search": "",
                    "fields": "INVESTING SCORE",
                    "type": "fundamental",
                    "date_start": "2026-03-23",
                    "date_end": "2026-03-23",
                    "order_by": "INVESTING SCORE",
                    "limit": 10,
                }
            ]
        )
        stage3_resp = MagicMock()
        stage3_resp.text = "Fallback analysis"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        mock_getSession.return_value.get.side_effect = Exception("Connection refused")

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        result = gen.executeWorkflow("Melhores ações")
        assert result == "Fallback analysis"

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_fetch_stock_data_exception(self, mock_genai, mock_config, mock_getSession):
        """fetchStockData exception path (lines 223-225)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = json.dumps(
            [
                {
                    "search": "PETR4",
                    "fields": "P/L",
                    "type": "fundamental",
                    "date_start": "2026-03-23",
                    "date_end": "2026-03-23",
                }
            ]
        )
        stage3_resp = MagicMock()
        stage3_resp.text = "Response after error"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        mock_getSession.return_value.get.side_effect = Exception("Timeout")

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        result = gen.executeWorkflow("P/L de PETR4")
        assert result == "Response after error"

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_fetch_stock_data_non_200(self, mock_genai, mock_config, mock_getSession):
        """fetchStockData non-200 status (line 222)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = json.dumps(
            [
                {
                    "search": "PETR4",
                    "fields": "P/L",
                    "type": "fundamental",
                    "date_start": "2026-03-23",
                    "date_end": "2026-03-23",
                }
            ]
        )
        stage3_resp = MagicMock()
        stage3_resp.text = "Response"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_getSession.return_value.get.return_value = mock_resp

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        result = gen.executeWorkflow("P/L de PETR4")
        assert result == "Response"

    @patch("main.app.prometheus.generation.PrometheusChatManager")
    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_execute_workflow_stage4_summary_update(self, mock_genai, mock_config, mock_getSession, mock_chat):
        """Stage 4: summary update when len(history) % 10 == 0 (lines 325-363)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = "[]"
        stage3_resp = MagicMock()
        stage3_resp.text = "Response"
        stage4_resp = MagicMock()
        stage4_resp.text = "Summary headline"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp, stage4_resp]

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()

        # History with exactly 10 messages to trigger Stage 4
        history = [{"role": "user", "parts": [{"text": f"msg{i}"}]} for i in range(10)]
        result = gen.executeWorkflow("oi", history=history, sessionId="sess-123", db=MagicMock())

        assert result == "Response"
        mock_chat.updateSummary.assert_called_once()
        mock_chat.updateSessionTitle.assert_called_once()

    @patch("main.app.prometheus.generation.getSession")
    @patch("main.app.prometheus.generation.Config")
    @patch("main.app.prometheus.generation.genai")
    def test_execute_workflow_global_request_status_not_200(self, mock_genai, mock_config, mock_getSession):
        """Global request with non-200 status (line 201-203 skipped)."""
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key"}
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"KEY": "", "KEY_SYSTEM": False, "HOST": "localhost", "PORT": 3200}

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        stage1_resp = MagicMock()
        stage1_resp.text = json.dumps(
            [
                {
                    "search": "",
                    "fields": "INVESTING SCORE",
                    "type": "fundamental",
                    "date_start": "2026-03-23",
                    "date_end": "2026-03-23",
                    "order_by": "INVESTING SCORE",
                    "limit": 10,
                }
            ]
        )
        stage3_resp = MagicMock()
        stage3_resp.text = "Analysis"
        mock_client.models.generate_content.side_effect = [stage1_resp, stage3_resp]

        mock_global_resp = MagicMock()
        mock_global_resp.status_code = 403  # Not 200
        mock_getSession.return_value.get.return_value = mock_global_resp

        from main.app.prometheus.generation import PrometheusGenerator

        gen = PrometheusGenerator()
        result = gen.executeWorkflow("Melhores ações")
        assert result == "Analysis"


# ---------------------------------------------------------------------------
# PrometheusChatManager (chat.py)
# ---------------------------------------------------------------------------


class TestPrometheusChatManager:
    """Cover all methods in chat.py (lines 11-120)."""

    def test_init(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mgr = PrometheusChatManager()
        assert mgr is not None

    def test_get_user_sessions(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()

        mock_session1 = MagicMock()
        mock_session1.sessionId = "s1"
        mock_session1.title = "Title 1"
        mock_session1.lastActivity = datetime(2026, 3, 23, 12, 0, 0)

        mock_session2 = MagicMock()
        mock_session2.sessionId = "s2"
        mock_session2.title = "Title 2"
        mock_session2.lastActivity = None

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_session1,
            mock_session2,
        ]

        result = PrometheusChatManager.getUserSessions(mock_db, userId=1)
        assert len(result) == 2
        assert result[0]["sessionId"] == "s1"
        assert result[0]["lastActivity"] == "2026-03-23T12:00:00"
        assert result[1]["lastActivity"] is None

    def test_create_session(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()

        result = PrometheusChatManager.createSession(mock_db, userId=1, title="Test")
        assert isinstance(result, str)
        assert len(result) > 0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_update_session_title_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.updateSessionTitle(mock_db, "sess-123", "New Title")
        assert result is True
        assert mock_session.title == "New Title"
        mock_db.commit.assert_called_once()

    def test_update_session_title_not_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.updateSessionTitle(mock_db, "nonexistent", "Title")
        assert result is False

    def test_save_message_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = []
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        PrometheusChatManager.saveMessage(mock_db, "sess-123", "user", "Hello", metadata={"key": "val"})

        assert len(mock_session.history) == 1
        assert mock_session.history[0]["role"] == "user"
        assert mock_session.history[0]["content"] == "Hello"
        assert mock_session.history[0]["metadata"] == {"key": "val"}
        mock_db.commit.assert_called_once()

    def test_save_message_history_none(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        PrometheusChatManager.saveMessage(mock_db, "sess-123", "assistant", "Reply")

        assert mock_session.history == [
            {
                "role": "assistant",
                "content": "Reply",
                "metadata": None,
                "timestamp": mock_session.history[0]["timestamp"],
            }
        ]

    def test_save_message_not_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        PrometheusChatManager.saveMessage(mock_db, "nonexistent", "user", "Hello")

    def test_get_history_with_messages(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = [
            {"role": "user", "content": "Hello", "timestamp": "2026-03-23T12:00:00"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2026-03-23T12:01:00"},
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.getHistory(mock_db, "sess-123")
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["parts"][0]["text"] == "Hello"
        assert result[1]["role"] == "model"

    def test_get_history_empty(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.getHistory(mock_db, "nonexistent")
        assert result == []

    def test_get_history_no_history(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.getHistory(mock_db, "sess-123")
        assert result == []

    def test_get_history_with_limit(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.history = [{"role": "user", "content": f"msg{i}"} for i in range(30)]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.getHistory(mock_db, "sess-123", limit=5)
        assert len(result) == 5

    def test_update_summary_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        PrometheusChatManager.updateSummary(mock_db, "sess-123", "New summary")
        assert mock_session.summary == "New summary"
        mock_db.commit.assert_called_once()

    def test_update_summary_not_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        PrometheusChatManager.updateSummary(mock_db, "nonexistent", "Summary")

    def test_delete_session_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = PrometheusChatManager.deleteSession(mock_db, "sess-123", userId=1)
        assert result is True
        mock_db.delete.assert_called_once_with(mock_session)
        mock_db.commit.assert_called_once()

    def test_delete_session_not_found(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.deleteSession(mock_db, "nonexistent", userId=1)
        assert result is False

    def test_verify_session_ownership_true(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = "sess-123"

        result = PrometheusChatManager.verifySessionOwnership(mock_db, "sess-123", userId=1)
        assert result is True

    def test_verify_session_ownership_false(self):
        from main.app.prometheus.chat import PrometheusChatManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = PrometheusChatManager.verifySessionOwnership(mock_db, "nonexistent", userId=1)
        assert result is False


# ---------------------------------------------------------------------------
# AuthenticationManager (authentication.py)
# ---------------------------------------------------------------------------


class TestAuthenticationManager:
    """Cover all methods in authentication.py (lines 13-75)."""

    @patch("main.app.authentication.authentication.hashPassword")
    def test_create_user_account_success(self, mock_hash):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_hash.return_value = "hashed_pw"

        result = AuthenticationManager.createUserAccount(mock_db, "newuser", "new@example.com", password="pass123")
        assert result is True
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_create_user_account_no_password_no_google(self):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "user", "e@e.com")
        assert exc_info.value.status_code == 400
        assert "password" in exc_info.value.detail.lower()

    def test_create_user_account_username_taken(self):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()
        existing = MagicMock()
        existing.username = "taken"
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "taken", "e@e.com", password="pass")
        assert exc_info.value.status_code == 400
        assert "Username already taken" in exc_info.value.detail

    def test_create_user_account_email_taken(self):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()
        existing = MagicMock()
        existing.username = "other"
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "newuser", "taken@example.com", password="pass")
        assert exc_info.value.status_code == 400
        assert "Email already registered" in exc_info.value.detail

    @patch("main.app.authentication.authentication.hashPassword")
    def test_create_user_account_db_exception(self, mock_hash):
        from main.app.authentication.authentication import AuthenticationManager
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit.side_effect = Exception("DB error")
        mock_hash.return_value = "hashed"

        with pytest.raises(HTTPException) as exc_info:
            AuthenticationManager.createUserAccount(mock_db, "user", "e@e.com", password="pass")
        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called()

    def test_create_user_account_with_google_id(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AuthenticationManager.createUserAccount(mock_db, "googleuser", "g@g.com", googleId="google-123")
        assert result is True

    def test_authenticate_google_user_found(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.userId = 1
        mock_user.username = "testuser"
        mock_user.getRolesList.return_value = ["USER"]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = AuthenticationManager.authenticateGoogleUser(mock_db, "google-123")
        assert result is not None
        assert result["userId"] == 1
        assert result["username"] == "testuser"

    def test_authenticate_google_user_not_found(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AuthenticationManager.authenticateGoogleUser(mock_db, "nonexistent")
        assert result is None

    def test_authenticate_google_user_exception(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        result = AuthenticationManager.authenticateGoogleUser(mock_db, "google-123")
        assert result is None

    @patch("main.app.authentication.authentication.verifyPassword")
    def test_authenticate_user_success(self, mock_verify):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.userId = 1
        mock_user.username = "testuser"
        mock_user.passwordHash = "hashed"
        mock_user.getRolesList.return_value = ["USER"]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_verify.return_value = True

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "pass123")
        assert result is not None
        assert result["userId"] == 1

    @patch("main.app.authentication.authentication.verifyPassword")
    def test_authenticate_user_wrong_password(self, mock_verify):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.passwordHash = "hashed"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_verify.return_value = False

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "wrong")
        assert result is None

    def test_authenticate_user_not_found(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AuthenticationManager.authenticateUser(mock_db, "nobody", "pass")
        assert result is None

    def test_authenticate_user_no_password_hash(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.passwordHash = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "pass")
        assert result is None

    def test_authenticate_user_exception(self):
        from main.app.authentication.authentication import AuthenticationManager

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        result = AuthenticationManager.authenticateUser(mock_db, "testuser", "pass")
        assert result is None


# ---------------------------------------------------------------------------
# SessionManager (session.py)
# ---------------------------------------------------------------------------


class TestSessionManager:
    """Cover all methods in session.py (lines 14-154)."""

    @patch("main.app.authentication.session.datetime")
    @patch("main.app.authentication.session.parseUserAgent")
    @patch("main.app.authentication.session.secrets")
    def test_create_session(self, mock_secrets, mock_parse_ua, mock_datetime):
        from main.app.authentication.session import SessionManager

        mock_secrets.token_urlsafe.return_value = "session-id-123"
        mock_secrets.token_hex.return_value = "a" * 64

        mock_device = MagicMock()
        mock_device.deviceType = "desktop"
        mock_device.browser = "Chrome"
        mock_device.os = "Windows"
        mock_parse_ua.return_value = mock_device

        mock_now = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone("America/Sao_Paulo"))
        mock_datetime.now.return_value = mock_now

        mock_db = MagicMock()
        mock_request = MagicMock()

        result = SessionManager.createSession(mock_db, userId=1, userAgent="Mozilla/5.0", request=mock_request)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result.sessionId == "session-id-123"

    @patch("main.app.authentication.session.datetime")
    @patch("main.app.authentication.session.parseUserAgent")
    @patch("main.app.authentication.session.secrets")
    def test_create_session_custom_expiry(self, mock_secrets, mock_parse_ua, mock_datetime):
        from main.app.authentication.session import SessionManager

        mock_secrets.token_urlsafe.return_value = "session-id-456"
        mock_secrets.token_hex.return_value = "b" * 64
        mock_parse_ua.return_value = MagicMock(deviceType="mobile", browser="Safari", os="iOS")

        mock_now = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone("America/Sao_Paulo"))
        mock_datetime.now.return_value = mock_now

        custom_expiry = mock_now + timedelta(days=7)
        mock_db = MagicMock()

        result = SessionManager.createSession(
            mock_db, userId=2, userAgent="Safari", request=MagicMock(), expiresAt=custom_expiry
        )
        assert result.expiresAt == custom_expiry

    def test_get_user_sessions_active_only(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        SessionManager.getUserSessions(mock_db, userId=1)

        query = mock_db.query.return_value.filter.return_value
        # Should have .filter().filter().order_by().limit().all()
        query.filter.return_value.order_by.return_value.limit.return_value.all.assert_called_once()

    def test_get_user_sessions_include_inactive(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        SessionManager.getUserSessions(mock_db, userId=1, includeInactive=True)

        # When includeInactive=True, only one filter is applied
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.assert_called_once()

    def test_get_session_by_id(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        SessionManager.getSessionById(mock_db, "sess-123", userId=1)

        query_filter = mock_db.query.return_value.filter.return_value
        query_filter.filter.return_value.first.assert_called_once()

    def test_get_session_by_id_no_user_id(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        SessionManager.getSessionById(mock_db, "sess-123")

        # With no userId, only one filter is applied
        mock_db.query.return_value.filter.return_value.first.assert_called_once()

    def test_get_current_session(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()

        result = SessionManager.getCurrentSession(mock_db, userId=1)

        mock_db.query.return_value.filter.return_value.order_by.return_value.first.assert_called_once()

    def test_revoke_session_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.revokeSession(mock_db, "sess-123", userId=1)
        assert result is True
        assert mock_session.isActive is False
        mock_db.commit.assert_called_once()

    def test_revoke_session_not_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

        result = SessionManager.revokeSession(mock_db, "nonexistent", userId=1)
        assert result is False

    def test_revoke_all_sessions(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        # revokeAllSessions: db.query(...).filter(userId, isActive).update(...)
        mock_db.query.return_value.filter.return_value.update.return_value = 5

        count = SessionManager.revokeAllSessions(mock_db, userId=1)
        assert count == 5
        mock_db.commit.assert_called_once()

    def test_revoke_all_sessions_with_except(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        # revokeAllSessions: db.query(...).filter(userId, isActive).filter(except).update(...)
        mock_db.query.return_value.filter.return_value.filter.return_value.update.return_value = 3

        count = SessionManager.revokeAllSessions(mock_db, userId=1, exceptSessionId="keep-this")
        assert count == 3

    def test_update_last_active_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.updateLastActive(mock_db, "sess-123")
        assert result is True
        mock_db.commit.assert_called_once()

    def test_update_last_active_not_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = SessionManager.updateLastActive(mock_db, "nonexistent")
        assert result is False

    @patch("main.app.authentication.session.datetime")
    def test_cleanup_expired_sessions(self, mock_datetime):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_now = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone("America/Sao_Paulo"))
        mock_datetime.now.return_value = mock_now
        mock_db.query.return_value.filter.return_value.update.return_value = 3

        count = SessionManager.cleanupExpiredSessions(mock_db)
        assert count == 3
        mock_db.commit.assert_called_once()

    @patch("main.app.authentication.session.datetime")
    def test_cleanup_expired_sessions_none_expired(self, mock_datetime):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_now = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone("America/Sao_Paulo"))
        mock_datetime.now.return_value = mock_now
        mock_db.query.return_value.filter.return_value.update.return_value = 0

        count = SessionManager.cleanupExpiredSessions(mock_db)
        assert count == 0

    def test_validate_session_active(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        mock_session.expiresAt = datetime(2026, 12, 31, tzinfo=timezone("America/Sao_Paulo"))
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is True

    def test_validate_session_not_found(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

        result = SessionManager.validateSession(mock_db, "nonexistent", userId=1)
        assert result is False

    def test_validate_session_inactive(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = False
        mock_session.expiresAt = datetime(2026, 12, 31, tzinfo=timezone("America/Sao_Paulo"))
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is False

    def test_validate_session_expired(self):
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        mock_session.expiresAt = datetime(2020, 1, 1, tzinfo=timezone("America/Sao_Paulo"))
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is False
        assert mock_session.isActive is False
        mock_db.commit.assert_called_once()

    def test_validate_session_expired_naive_tz(self):
        """Exercises the tzinfo-is-None branch (line 144-148)."""
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        # Naive datetime (no timezone)
        mock_session.expiresAt = datetime(2020, 1, 1)
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is False

    def test_validate_session_no_expiry(self):
        """Exercises the expiresAt-is-None branch (line 143)."""
        from main.app.authentication.session import SessionManager

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.isActive = True
        mock_session.expiresAt = None
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_session

        result = SessionManager.validateSession(mock_db, "sess-123", userId=1)
        assert result is True


# ---------------------------------------------------------------------------
# SSO (sso.py)
# ---------------------------------------------------------------------------


class TestSSO:
    """Cover getGoogleSSO (lines 6-14)."""

    @patch("main.app.authentication.sso.Config")
    @patch("main.app.authentication.sso.GoogleSSO")
    def test_get_google_sso_with_redirect(self, mock_google_sso, mock_config):
        from main.app.authentication.sso import getGoogleSSO

        mock_config.USER = {
            "GOOGLE_CLIENT_ID": "cid",
            "GOOGLE_CLIENT_SECRET": "csecret",
            "GOOGLE_REDIRECT_URI": "http://callback",
        }

        result = getGoogleSSO(redirectUri="http://custom-callback")

        mock_google_sso.assert_called_once_with(
            client_id="cid",
            client_secret="csecret",
            redirect_uri="http://custom-callback",
        )

    @patch("main.app.authentication.sso.Config")
    @patch("main.app.authentication.sso.GoogleSSO")
    def test_get_google_sso_default_redirect(self, mock_google_sso, mock_config):
        from main.app.authentication.sso import getGoogleSSO

        mock_config.USER = {
            "GOOGLE_CLIENT_ID": "cid",
            "GOOGLE_CLIENT_SECRET": "csecret",
            "GOOGLE_REDIRECT_URI": "http://default-callback",
        }

        result = getGoogleSSO()

        mock_google_sso.assert_called_once_with(
            client_id="cid",
            client_secret="csecret",
            redirect_uri="http://default-callback",
        )
