"""Pagination boundary tests against the real GET /prometheus/sessions endpoint.

Replaces the deleted synthetic `/items` app tests with equivalent assertions
against the real Query(ge/le) guards in main/controller/prometheus_controller.py:
`limit: int = Query(20, ge=1, le=100)`, `offset: int = Query(0, ge=0)`.
"""

import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tests.conftest import make_prometheus_client


def makeSessions(count: int) -> list[dict]:
    return [{"sessionId": f"s{i}", "title": f"Chat {i}"} for i in range(count)]


class TestPrometheusSessionsPagination:
    def test_defaults(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(50)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions")
            assert resp.status_code == 200
            body = resp.json()
            assert body["limit"] == 20
            assert body["offset"] == 0
            assert body["total"] == 50
            assert len(body["sessions"]) == 20

    def test_customLimit(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(50)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?limit=5")
            body = resp.json()
            assert resp.status_code == 200
            assert body["limit"] == 5
            assert len(body["sessions"]) == 5

    def test_customOffset(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(50)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?offset=10")
            body = resp.json()
            assert resp.status_code == 200
            assert body["offset"] == 10
            assert len(body["sessions"]) == 20
            assert body["sessions"][0]["sessionId"] == "s10"

    def test_limitAndOffset(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(100)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?limit=10&offset=50")
            body = resp.json()
            assert resp.status_code == 200
            assert body["limit"] == 10
            assert body["offset"] == 50
            assert len(body["sessions"]) == 10
            assert body["sessions"][0]["sessionId"] == "s50"

    def test_limitExceedsMaxRejected(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(150)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?limit=101")
            assert resp.status_code == 422

    def test_limitZeroRejected(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(50)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?limit=0")
            assert resp.status_code == 422

    def test_limitNegativeRejected(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(50)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?limit=-1")
            assert resp.status_code == 422

    def test_negativeOffsetRejected(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(50)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?offset=-1")
            assert resp.status_code == 422

    def test_offsetBeyondTotal(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(50)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?offset=200")
            body = resp.json()
            assert resp.status_code == 200
            assert body["sessions"] == []
            assert body["total"] == 50

    def test_limitEqualsMax(self):
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mockPcm:
            mockPcm.getUserSessions.return_value = makeSessions(150)
            client, _, _ = make_prometheus_client()
            resp = client.get("/prometheus/sessions?limit=100")
            body = resp.json()
            assert resp.status_code == 200
            assert body["limit"] == 100
            assert len(body["sessions"]) == 100
