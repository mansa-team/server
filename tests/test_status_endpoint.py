"""Tests for run.py /status endpoint — covers status response structure."""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def statusClient():
    """Create a test client for the status endpoint without running lifespan."""
    from run import app

    return TestClient(app, raise_server_exceptions=False)


class TestStatusEndpoint:
    def test_status_returns_200(self, statusClient):
        resp = statusClient.get("/status")
        assert resp.status_code == 200

    def test_status_has_healthy(self, statusClient):
        data = statusClient.get("/status").json()
        assert data["status"] == "healthy"

    def test_status_has_uptime_format(self, statusClient):
        data = statusClient.get("/status").json()
        uptime = data["uptime"]
        assert "d" in uptime and "h" in uptime and "m" in uptime and "s" in uptime

    def test_status_has_services_dict(self, statusClient):
        data = statusClient.get("/status").json()
        assert "services" in data
        assert isinstance(data["services"], dict)

    def test_status_services_contain_expected_keys(self, statusClient):
        data = statusClient.get("/status").json()
        services = data["services"]
        for name in ["authentication", "user", "stocks_api", "prometheus", "scraper"]:
            assert name in services, f"Missing service: {name}"

    def test_status_local_service_has_port_and_type(self, statusClient):
        data = statusClient.get("/status").json()
        # Find first enabled service
        for name, svc in data["services"].items():
            if svc.get("status") == "running" and name != "scraper":
                assert "port" in svc
                assert "type" in svc
                assert svc["type"] in ("local", "remote")
                break

    def test_status_disabled_service(self, statusClient):
        data = statusClient.get("/status").json()
        for name, svc in data["services"].items():
            if svc.get("status") == "disabled":
                assert "port" not in svc

    def test_status_scraper_no_port(self, statusClient):
        data = statusClient.get("/status").json()
        scraper = data["services"].get("scraper", {})
        if scraper.get("status") == "running":
            assert "port" not in scraper

    def test_health_endpoint(self, statusClient):
        resp = statusClient.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestScraperTrigger:
    def test_scraper_trigger_debug_mode(self, statusClient):
        with patch("run.Config") as mockConfig, patch("run.runScraper"):
            mockConfig.DEBUG_MODE = True
            resp = statusClient.post("/scraper/run")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_scraper_trigger_not_debug(self, statusClient):
        with patch("run.Config") as mockConfig, patch("run.runScraper"):
            mockConfig.DEBUG_MODE = False
            resp = statusClient.post("/scraper/run")
            assert resp.status_code == 200
            assert resp.json()["status"] == "error"
