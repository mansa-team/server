from unittest.mock import patch

import pytest

from main.app.prometheus import sandbox as sandboxModule


class TestSandboxAuthGating:
    def test_urlSetEmptyTokenRaises(self):
        with (
            patch.object(sandboxModule.Config.PROMETHEUS, "FORGEVM_URL", "http://forgevm:7423"),
            patch.object(sandboxModule.Config.PROMETHEUS, "FORGEVM_API_TOKEN", ""),
        ):
            with pytest.raises(RuntimeError, match="FORGEVM_API_TOKEN"):
                sandboxModule.getClient()

    def test_urlSetWithTokenPassesThrough(self):
        with (
            patch.object(sandboxModule.Config.PROMETHEUS, "FORGEVM_URL", "http://forgevm:7423"),
            patch.object(sandboxModule.Config.PROMETHEUS, "FORGEVM_API_TOKEN", "secret"),
            patch.object(sandboxModule, "AsyncClient") as mockClient,
        ):
            client = sandboxModule.getClient()
            mockClient.assert_called_once_with(base_url="http://forgevm:7423", api_key="secret", timeout=30)
            assert client is mockClient.return_value

    def test_urlUnsetReturnsClient(self):
        with (
            patch.object(sandboxModule.Config.PROMETHEUS, "FORGEVM_URL", ""),
            patch.object(sandboxModule.Config.PROMETHEUS, "FORGEVM_API_TOKEN", ""),
            patch.object(sandboxModule, "AsyncClient") as mockClient,
        ):
            client = sandboxModule.getClient()
            mockClient.assert_called_once_with(base_url="", api_key=None, timeout=30)
            assert client is mockClient.return_value
