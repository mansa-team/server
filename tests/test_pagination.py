"""Tests for pagination utility (utils/pagination.py)."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Depends
from starlette.testclient import TestClient
from main.utils.pagination import PaginationParams


@pytest.fixture
def app():
    application = FastAPI()

    @application.get("/items")
    def list_items(pagination: PaginationParams = Depends()):
        all_items = list(range(100))  # 100 fake items
        page = all_items[pagination.offset : pagination.offset + pagination.limit]
        return {
            "items": page,
            "total": len(all_items),
            "limit": pagination.limit,
            "offset": pagination.offset,
        }

    return application


@pytest.fixture
def client(app):
    return TestClient(app)


class TestPaginationParams:
    def test_defaults(self, client):
        response = client.get("/items")
        body = response.json()
        assert response.status_code == 200
        assert body["limit"] == 20  # default
        assert body["offset"] == 0  # default
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
        assert body["items"][0] == 10  # first item after skipping 10

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
