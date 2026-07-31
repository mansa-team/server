"""Tests for main/utils/connectivity.py — covers all branches."""

from unittest.mock import patch, MagicMock
import pytest
from requests.exceptions import ConnectionError, Timeout, RequestException


class TestCheckMySqlConnection:
    """checkDatabaseConnection — success, errors, engine=None paths."""

    @patch("main.utils.connectivity.stocksEngine", MagicMock())
    @patch("main.utils.connectivity.engine")
    def test_both_engines_ok(self, mockEngine):
        mockConn = MagicMock()
        mockEngine.connect.return_value.__enter__ = MagicMock(return_value=mockConn)
        mockEngine.connect.return_value.__exit__ = MagicMock(return_value=False)

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["user_db"]["status"] == "connected"
        assert result["stocks_db"]["status"] == "connected"
        mockConn.execute.assert_called_once()

    @patch("main.utils.connectivity.stocksEngine", MagicMock())
    @patch("main.utils.connectivity.engine")
    def test_user_db_connection_error(self, mockEngine):
        mockEngine.connect.side_effect = ConnectionError("refused")

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["user_db"]["status"] == "error"

    @patch("main.utils.connectivity.stocksEngine", MagicMock())
    @patch("main.utils.connectivity.engine")
    def test_user_db_timeout(self, mockEngine):
        mockEngine.connect.side_effect = Timeout("timed out")

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["user_db"]["status"] == "error"

    @patch("main.utils.connectivity.stocksEngine", MagicMock())
    @patch("main.utils.connectivity.engine")
    def test_user_db_generic_exception(self, mockEngine):
        mockEngine.connect.side_effect = RuntimeError("something broke")

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["user_db"]["status"] == "error"

    @patch("main.utils.connectivity.engine", None)
    @patch("main.utils.connectivity.stocksEngine", MagicMock())
    def test_user_engine_none(self):
        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["user_db"]["status"] == "not_configured"

    @patch("main.utils.connectivity.engine")
    @patch("main.utils.connectivity.stocksEngine")
    def test_stocks_db_connection_error(self, mockStocks, mockUser):
        mockUserConn = MagicMock()
        mockUser.connect.return_value.__enter__ = MagicMock(return_value=mockUserConn)
        mockUser.connect.return_value.__exit__ = MagicMock(return_value=False)
        mockStocks.connect.side_effect = ConnectionError("refused")

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["stocks_db"]["status"] == "error"

    @patch("main.utils.connectivity.engine")
    @patch("main.utils.connectivity.stocksEngine")
    def test_stocks_db_timeout(self, mockStocks, mockUser):
        mockUserConn = MagicMock()
        mockUser.connect.return_value.__enter__ = MagicMock(return_value=mockUserConn)
        mockUser.connect.return_value.__exit__ = MagicMock(return_value=False)
        mockStocks.connect.side_effect = Timeout("timed out")

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["stocks_db"]["status"] == "error"

    @patch("main.utils.connectivity.engine")
    @patch("main.utils.connectivity.stocksEngine")
    def test_stocks_db_generic_exception(self, mockStocks, mockUser):
        mockUserConn = MagicMock()
        mockUser.connect.return_value.__enter__ = MagicMock(return_value=mockUserConn)
        mockUser.connect.return_value.__exit__ = MagicMock(return_value=False)
        mockStocks.connect.side_effect = RuntimeError("broke")

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["stocks_db"]["status"] == "error"

    @patch("main.utils.connectivity.engine")
    @patch("main.utils.connectivity.stocksEngine", None)
    def test_stocks_engine_none(self, mockUser):
        mockConn = MagicMock()
        mockUser.connect.return_value.__enter__ = MagicMock(return_value=mockConn)
        mockUser.connect.return_value.__exit__ = MagicMock(return_value=False)

        from main.utils.connectivity import checkDatabaseConnection

        result = checkDatabaseConnection()
        assert result["stocks_db"]["status"] == "not_configured"


class TestCheckServiceConnection:
    """checkServiceConnection — success, not found, errors."""

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_service_not_found(self, mockConfig, mockGetSession):
        mockConfig.USER = None
        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("USER")
        assert result is False

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_stocks_api_health_ok(self, mockConfig, mockGetSession):
        mockConfig.STOCKS_API = {"HOST": "127.0.0.1", "PORT": "3201"}
        mockResp = MagicMock()
        mockResp.status_code = 200
        mockGetSession.return_value.get.return_value = mockResp

        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("STOCKS_API")
        assert result is True
        mockGetSession.return_value.get.assert_called_once_with("http://127.0.0.1:3201/stocks/health", timeout=5)

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_non_stocks_prefix(self, mockConfig, mockGetSession):
        mockConfig.USER = {"HOST": "127.0.0.1", "PORT": "3200"}
        mockResp = MagicMock()
        mockResp.status_code = 200
        mockGetSession.return_value.get.return_value = mockResp

        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("USER")
        assert result is True
        mockGetSession.return_value.get.assert_called_once_with("http://127.0.0.1:3200/user/health", timeout=5)

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_non_200_status(self, mockConfig, mockGetSession):
        mockConfig.USER = {"HOST": "127.0.0.1", "PORT": "3200"}
        mockResp = MagicMock()
        mockResp.status_code = 503
        mockGetSession.return_value.get.return_value = mockResp

        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("USER")
        assert not result

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_connection_error(self, mockConfig, mockGetSession):
        mockConfig.USER = {"HOST": "127.0.0.1", "PORT": "3200"}
        mockGetSession.return_value.get.side_effect = ConnectionError("refused")

        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("USER")
        assert result is False

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_timeout(self, mockConfig, mockGetSession):
        mockConfig.USER = {"HOST": "127.0.0.1", "PORT": "3200"}
        mockGetSession.return_value.get.side_effect = Timeout("slow")

        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("USER")
        assert result is False

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_request_exception(self, mockConfig, mockGetSession):
        mockConfig.USER = {"HOST": "127.0.0.1", "PORT": "3200"}
        mockGetSession.return_value.get.side_effect = RequestException("bad request")

        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("USER")
        assert result is False

    @patch("main.utils.connectivity.getSession")
    @patch("main.utils.connectivity.Config")
    def test_generic_exception(self, mockConfig, mockGetSession):
        mockConfig.USER = {"HOST": "127.0.0.1", "PORT": "3200"}
        mockGetSession.return_value.get.side_effect = RuntimeError("unexpected")

        from main.utils.connectivity import checkServiceConnection

        result = checkServiceConnection("USER")
        assert result is False
