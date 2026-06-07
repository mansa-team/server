import pytest
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from starlette.testclient import TestClient
from fastapi import FastAPI
from main.utils.request_id import RequestIDMiddleware, request_id_var


@pytest.fixture
def app():
    application = FastAPI()
    application.add_middleware(RequestIDMiddleware)

    @application.get("/test")
    def test_route():
        return {"request_id": request_id_var.get()}

    @application.get("/echo")
    def echo_route():
        return {"id": request_id_var.get()}

    return application


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRequestIDMiddleware:
    def test_generates_uuid_when_no_header(self, client):
        response = client.get("/test")
        assert response.status_code == 200
        rid = response.headers.get("X-Request-ID")
        assert rid is not None
        # Should be a valid UUID4
        parsed = uuid.UUID(rid)
        assert parsed.version == 4

    def test_returns_generated_uuid_in_body(self, client):
        response = client.get("/test")
        body = response.json()
        rid = body["request_id"]
        parsed = uuid.UUID(rid)
        assert parsed.version == 4

    def test_uses_client_provided_request_id(self, client):
        client_id = str(uuid.uuid4())
        response = client.get("/test", headers={"X-Request-ID": client_id})
        assert response.headers["X-Request-ID"] == client_id
        assert response.json()["request_id"] == client_id

    def test_response_header_matches_request(self, client):
        client_id = "my-custom-id-12345"
        response = client.get("/test", headers={"X-Request-ID": client_id})
        assert response.headers["X-Request-ID"] == client_id

    def test_different_requests_get_different_ids(self, client):
        r1 = client.get("/test")
        r2 = client.get("/test")
        assert r1.json()["request_id"] != r2.json()["request_id"]

    def test_context_var_available_in_route(self, client):
        client_id = "context-test-id"
        response = client.get("/echo", headers={"X-Request-ID": client_id})
        assert response.json()["id"] == client_id

    def test_empty_x_request_id_header_generates_uuid(self, client):
        # Empty string should be treated as missing
        response = client.get("/test", headers={"X-Request-ID": ""})
        rid = response.headers["X-Request-ID"]
        # Should generate a UUID, not return empty
        assert rid != ""
        parsed = uuid.UUID(rid)
        assert parsed.version == 4

    def test_middleware_preserves_response_body(self, client):
        response = client.get("/test")
        assert response.status_code == 200
        body = response.json()
        assert "request_id" in body
