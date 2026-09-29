import pytest
from config import Config, StocksApiSettings, OrunmilaSettings, ScraperSettings


class TestConfig:
    def test_stocks_api_attributes(self):
        settings = StocksApiSettings()
        assert settings.KEY_SYSTEM is not None
        assert settings.KEY is not None

    def test_orunmila_attributes(self):
        settings = OrunmilaSettings()
        assert settings.GEMINI_API_KEY is not None

    def test_scraper_attributes(self):
        settings = ScraperSettings()
        assert settings.ENABLED is not None
