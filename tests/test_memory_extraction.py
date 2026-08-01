import json
from unittest.mock import MagicMock, patch

import pytest

from google.genai import types

from main.app.prometheus.memory import (
    MEMORY_EXTRACTION_TOKEN_BUDGET,
    PrometheusMemory,
)


@pytest.fixture
def db(dbSession):
    return dbSession


def makeHistory(count, text="olá mundo " * 20):
    return [{"role": "user" if i % 2 == 0 else "model", "parts": [{"text": text}]} for i in range(count)]


class FakeMemory:
    def __init__(self):
        self.calls = 0

    def upsertMemory(self, db, userId, **kwargs):
        self.calls += 1
        return {"status": "created", "memory": type("M", (), {"id": 1})()}


class FakeResponse:
    text = json.dumps([{"key": "estilo", "value": "value investing", "type": "preference"}])


def makeClient(result_count=1):
    client = type("C", (), {})()
    client.models = type("M", (), {})()
    resp = FakeResponse()
    resp.text = json.dumps([{"key": f"k{i}", "value": f"v{i}", "type": "context"} for i in range(result_count)])

    def generate_content(**kw):
        client.last_config = kw.get("config")
        return resp

    client.models.generate_content = generate_content
    return client


def freeAccess(roles, perm):
    return perm.name != "PROMETHEUS_EXTENDED_MEMORIES"


def premiumAccess(roles, perm):
    return True


def test_no_prometheus_access_skips_without_api_call(db):
    with (
        patch("main.app.prometheus.memory.Roles.checkAccess", return_value=False) as ca,
        patch("main.app.prometheus.memory.getClient") as gc,
    ):
        assert PrometheusMemory.extract(db, 1, "s1", ["USER"]) == []
        ca.assert_called()
        gc.assert_not_called()


def test_below_token_budget_skips_api_call(db):
    with (
        patch("main.app.prometheus.memory.Roles.checkAccess", side_effect=premiumAccess),
        patch("main.app.prometheus.chat.PrometheusChatManager.getHistory", return_value=makeHistory(2)),
        patch("main.app.prometheus.memory.getClient") as gc,
        patch("main.app.prometheus.memory.PrometheusMemory.countMemories", return_value=0),
    ):
        assert PrometheusMemory.extract(db, 1, "s1", ["PREMIUM"]) == []
        gc.assert_not_called()


def test_at_budget_calls_api_and_upserts_inferred(db):
    client = makeClient()
    with (
        patch("main.app.prometheus.memory.Roles.checkAccess", side_effect=premiumAccess),
        patch(
            "main.app.prometheus.chat.PrometheusChatManager.getHistory", return_value=makeHistory(3, "palavra " * 3000)
        ),
        patch("main.app.prometheus.memory.countTokens", return_value=MEMORY_EXTRACTION_TOKEN_BUDGET),
        patch("main.app.prometheus.memory.embed", return_value=[object()]),
        patch("main.app.prometheus.memory.getClient", return_value=client),
        patch("main.app.prometheus.memory.PrometheusMemory.countMemories", return_value=0),
        patch(
            "main.app.prometheus.memory.PrometheusMemory.upsertMemory", new=MagicMock(wraps=FakeMemory().upsertMemory)
        ) as up,
    ):
        result = PrometheusMemory.extract(db, 1, "s1", ["PREMIUM"])
        assert result
        assert up.call_args.kwargs["source"] == "inferred"

        schema = client.last_config.response_schema
        assert schema is not None
        assert schema.type == types.Type.ARRAY
        assert schema.items.type == types.Type.OBJECT
        assert schema.items.required == ["key", "value", "type"]
        assert set(schema.items.properties["type"].enum) == {"preference", "analysis", "feedback", "context"}


def test_free_users_get_at_most_5_upserts(db):
    fake = FakeMemory()
    with (
        patch("main.app.prometheus.memory.Roles.checkAccess", side_effect=freeAccess),
        patch(
            "main.app.prometheus.chat.PrometheusChatManager.getHistory", return_value=makeHistory(3, "palavra " * 3000)
        ),
        patch("main.app.prometheus.memory.countTokens", return_value=MEMORY_EXTRACTION_TOKEN_BUDGET),
        patch("main.app.prometheus.memory.embed", return_value=[object()]),
        patch("main.app.prometheus.memory.getClient", return_value=makeClient(12)),
        patch("main.app.prometheus.memory.PrometheusMemory.countMemories", return_value=0),
        patch("main.app.prometheus.memory.PrometheusMemory.upsertMemory", new=fake.upsertMemory),
    ):
        PrometheusMemory.extract(db, 1, "s1", ["USER"])
        assert fake.calls == 5


def test_premium_users_get_at_most_10_upserts(db):
    fake = FakeMemory()
    with (
        patch("main.app.prometheus.memory.Roles.checkAccess", side_effect=premiumAccess),
        patch(
            "main.app.prometheus.chat.PrometheusChatManager.getHistory", return_value=makeHistory(3, "palavra " * 3000)
        ),
        patch("main.app.prometheus.memory.countTokens", return_value=MEMORY_EXTRACTION_TOKEN_BUDGET),
        patch("main.app.prometheus.memory.embed", return_value=[object()]),
        patch("main.app.prometheus.memory.getClient", return_value=makeClient(12)),
        patch("main.app.prometheus.memory.PrometheusMemory.countMemories", return_value=0),
        patch("main.app.prometheus.memory.PrometheusMemory.upsertMemory", new=fake.upsertMemory),
    ):
        PrometheusMemory.extract(db, 1, "s1", ["PREMIUM"])
        assert fake.calls == 10


def test_non_list_llm_response_returns_empty_without_raising(db):
    client = type("C", (), {})()
    client.models = type("M", (), {})()
    resp = FakeResponse()
    resp.text = json.dumps({"memories": [{"key": "a", "value": "b", "type": "context"}]})
    client.models.generate_content = lambda **kw: resp
    with (
        patch("main.app.prometheus.memory.Roles.checkAccess", side_effect=premiumAccess),
        patch(
            "main.app.prometheus.chat.PrometheusChatManager.getHistory", return_value=makeHistory(3, "palavra " * 3000)
        ),
        patch("main.app.prometheus.memory.countTokens", return_value=MEMORY_EXTRACTION_TOKEN_BUDGET),
        patch("main.app.prometheus.memory.embed", return_value=[object()]),
        patch("main.app.prometheus.memory.getClient", return_value=client),
        patch("main.app.prometheus.memory.PrometheusMemory.countMemories", return_value=0),
        patch("main.app.prometheus.memory.PrometheusMemory.upsertMemory", new=FakeMemory().upsertMemory),
    ):
        assert PrometheusMemory.extract(db, 1, "s1", ["PREMIUM"]) == []
