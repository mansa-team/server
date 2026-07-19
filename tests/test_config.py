import pytest
from config import Config, StocksApiSettings, PrometheusSettings, ScraperSettings


class TestConfig:
    def test_stocks_api_getitem(self):
        settings = StocksApiSettings()
        # Test __getitem__ mapping
        assert settings["KEY_SYSTEM"] == settings.KEY_SYSTEM
        assert settings["DEFAULT_QUOTA"] == settings.DEFAULT_QUOTA

    def test_prometheus_getitem(self):
        settings = PrometheusSettings()
        # Test __getitem__ mapping
        assert settings["GEMINI_API_KEY"] == settings.GEMINI_API_KEY

    def test_scraper_getitem(self):
        settings = ScraperSettings()
        # Test __getitem__ returns getattr
        assert settings["ENABLED"] == settings.ENABLED
