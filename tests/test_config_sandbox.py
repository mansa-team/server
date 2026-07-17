import pytest
from config import PrometheusSettings


class TestSandboxConfig:
    def test_sandbox_defaults(self):
        settings = PrometheusSettings()
        assert settings.SANDBOX_HOST == "localhost"
        assert settings.SANDBOX_PORT == 8080
        assert settings.SANDBOX_TEMPLATE == "python-data-science"
        assert settings.WORKSPACE_ROOT == "/workspace"

    def test_sandbox_fields_exist(self):
        settings = PrometheusSettings()
        # Verify fields are accessible
        assert hasattr(settings, "SANDBOX_HOST")
        assert hasattr(settings, "SANDBOX_PORT")
        assert hasattr(settings, "SANDBOX_TEMPLATE")
        assert hasattr(settings, "WORKSPACE_ROOT")

    def test_sandbox_types(self):
        settings = PrometheusSettings()
        assert isinstance(settings.SANDBOX_HOST, str)
        assert isinstance(settings.SANDBOX_PORT, int)
        assert isinstance(settings.SANDBOX_TEMPLATE, str)
        assert isinstance(settings.WORKSPACE_ROOT, str)
