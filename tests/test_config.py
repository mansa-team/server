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

    def test_base_mansa_settings_get(self):
        from config import BaseMansaSettings

        class TestSettings(BaseMansaSettings):
            TEST_VALUE: str = "test"

            def __getitem__(self, item):
                if item == "MISSING_KEY":
                    raise KeyError(item)
                if item == "MISSING_ATTR":
                    raise AttributeError(item)
                return getattr(self, item, None)

        settings = TestSettings()
        # Test get method - existing key
        assert settings.get("TEST_VALUE") == "test"
        # Test KeyError path
        assert settings.get("MISSING_KEY", "default") == "default"
        # Test AttributeError path
        assert settings.get("MISSING_ATTR", "default") == "default"
