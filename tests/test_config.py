import pytest
from config import Config, StocksApiSettings, PrometheusSettings, ScraperSettings


class TestConfig:
    def test_stocks_api_attributes(self):
        settings = StocksApiSettings()
        assert settings.KEY_SYSTEM is not None
        assert settings.DEFAULT_QUOTA is not None

    def test_prometheus_attributes(self):
        settings = PrometheusSettings()
        assert settings.GEMINI_API_KEY is not None

    def test_scraper_attributes(self):
        settings = ScraperSettings()
        assert settings.ENABLED is not None
