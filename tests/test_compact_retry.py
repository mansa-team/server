from unittest.mock import patch, MagicMock
import main.app.prometheus.compact as compactMod
from main.app.prometheus.compact import loadFieldData


class TestLoadFieldDataRetry:
    def test_retryAfterFailure(self):
        compactMod.fieldData = None
        fakeResponse = MagicMock()
        fakeResponse.json.return_value = {"historical": {"LUCRO LIQUIDO": [2023]}, "fundamental": ["P/L"]}
        mockSession = MagicMock()
        mockSession.get.side_effect = [Exception("boom"), fakeResponse]
        with patch("main.app.prometheus.compact.getSession", return_value=mockSession):
            first = loadFieldData()
            assert first == {"historical": [], "fundamental": []}
            assert compactMod.fieldData is None
            second = loadFieldData()
            assert "LUCRO LIQUIDO" in second["historical"]
            assert second["fundamental"] == ["P/L"]
        compactMod.fieldData = None
