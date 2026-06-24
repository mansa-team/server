"""Tests for stocks API field validation — verifies the fields parameter
accepts all valid field names returned by /stocks/fields, including
`/` (P/L) and `.` (MARG. LIQUIDA).
"""
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# The fixed pattern — allows uppercase, digits, comma, whitespace, /, ., -, :
FIELDS_PATTERN = r"^[A-Z0-9,\s/.:-]+$"


class TestFieldRegexPattern:
    """Direct tests on the regex pattern used for the `fields` query param."""

    def test_slash_in_field_name(self):
        """P/L must be accepted — it's a standard valuation metric."""
        assert re.match(FIELDS_PATTERN, "P/L") is not None

    def test_dot_in_field_name(self):
        """MARG. LIQUIDA must be accepted — returned by /stocks/fields."""
        assert re.match(FIELDS_PATTERN, "MARG. LIQUIDA") is not None

    def test_slash_and_dot_combined(self):
        """P/VP and similar combos must be accepted."""
        assert re.match(FIELDS_PATTERN, "P/VP") is not None

    def test_normal_field_still_works(self):
        """Basic fields like ROE must still pass."""
        assert re.match(FIELDS_PATTERN, "ROE") is not None

    def test_comma_separated_with_slash(self):
        """Comma-separated list containing slash fields must pass."""
        assert re.match(FIELDS_PATTERN, "P/L,ROE,DY") is not None

    def test_rejects_script_injection(self):
        """Pattern must reject potential injection — no angle brackets."""
        assert re.match(FIELDS_PATTERN, "<script>") is None
        assert re.match(FIELDS_PATTERN, "ROE; DROP TABLE") is None


# ---------------------------------------------------------------------------
# 2. Integration tests — FastAPI TestClient with validation
# ---------------------------------------------------------------------------

@pytest.fixture()
def stocks_client():
    """Minimal TestClient with just the stocks router for validation tests."""
    from main.controller.stocksapi_controller import router as stocksRouter

    app = FastAPI()
    app.include_router(stocksRouter)

    # Mock verifyAPIKey so tests aren't blocked by missing API key
    from main.app.stocks_api.key import verifyAPIKey

    def _mock_verify():
        return "test-key"

    app.dependency_overrides[verifyAPIKey] = _mock_verify

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestFundamentalFieldValidation:
    """Integration: /stocks/fundamental must accept slash and dot fields."""

    def test_pslashl_not_422(self, stocks_client):
        """GET /fundamental?fields=P/L must not return 422 (validation error)."""
        resp = stocks_client.get("/stocks/fundamental", params={"fields": "P/L"})
        assert resp.status_code != 422, f"Got 422: {resp.json()}"

    def test_dot_field_not_422(self, stocks_client):
        """GET /fundamental?fields=MARG. LIQUIDA must not return 422."""
        resp = stocks_client.get("/stocks/fundamental", params={"fields": "MARG. LIQUIDA"})
        assert resp.status_code != 422, f"Got 422: {resp.json()}"

    def test_mixed_fields_not_422(self, stocks_client):
        """GET /fundamental?fields=P/L,ROE,DY must not return 422."""
        resp = stocks_client.get("/stocks/fundamental", params={"fields": "P/L,ROE,DY"})
        assert resp.status_code != 422, f"Got 422: {resp.json()}"


class TestHistoricalFieldValidation:
    """Integration: /stocks/historical must accept slash and dot fields."""

    def test_pslashl_not_422(self, stocks_client):
        """GET /historical?fields=P/L must not return 422."""
        resp = stocks_client.get("/stocks/historical", params={"fields": "P/L"})
        assert resp.status_code != 422, f"Got 422: {resp.json()}"

    def test_dot_field_not_422(self, stocks_client):
        """GET /historical?fields=MARG. LIQUIDA must not return 422."""
        resp = stocks_client.get("/stocks/historical", params={"fields": "MARG. LIQUIDA"})
        assert resp.status_code != 422, f"Got 422: {resp.json()}"

    def test_comma_separated_with_slash_not_422(self, stocks_client):
        """GET /historical?fields=LUCRO LIQUIDO,P/L must not return 422."""
        resp = stocks_client.get("/stocks/historical", params={"fields": "LUCRO LIQUIDO,P/L"})
        assert resp.status_code != 422, f"Got 422: {resp.json()}"
