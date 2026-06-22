"""Tests for inline pagination params (used in user + prometheus controllers)."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Depends, Query
from starlette.testclient import TestClient


@pytest.fixture
def app():
    application = FastAPI()

    @application.get("/items")
    def list_items(
        limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
    ):
        all_items = list(range(100))
        page = all_items[offset : offset + limit]
        return {
            "items": page,
            "total": len(all_items),
            "limit": limit,
            "offset": offset,
        }

    return application


@pytest.fixture
def client(app):
    return TestClient(app)


class TestInlinePagination:
    def test_defaults(self, client):
        response = client.get("/items")
        body = response.json()
        assert response.status_code == 200
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert len(body["items"]) == 20

    def test_custom_limit(self, client):
        response = client.get("/items?limit=5")
        body = response.json()
        assert body["limit"] == 5
        assert len(body["items"]) == 5

    def test_custom_offset(self, client):
        response = client.get("/items?offset=10")
        body = response.json()
        assert body["offset"] == 10
        assert len(body["items"]) == 20
        assert body["items"][0] == 10

    def test_limit_and_offset(self, client):
        response = client.get("/items?limit=10&offset=50")
        body = response.json()
        assert body["limit"] == 10
        assert body["offset"] == 50
        assert len(body["items"]) == 10
        assert body["items"][0] == 50

    def test_limit_exceeds_max_rejected(self, client):
        response = client.get("/items?limit=101")
        assert response.status_code == 422

    def test_limit_zero_rejected(self, client):
        response = client.get("/items?limit=0")
        assert response.status_code == 422

    def test_negative_offset_rejected(self, client):
        response = client.get("/items?offset=-1")
        assert response.status_code == 422

    def test_offset_beyond_total(self, client):
        response = client.get("/items?offset=200")
        body = response.json()
        assert body["items"] == []

    def test_limit_equals_max(self, client):
        response = client.get("/items?limit=100")
        body = response.json()
        assert body["limit"] == 100
        assert len(body["items"]) == 100
