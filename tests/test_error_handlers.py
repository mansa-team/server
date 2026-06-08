"""Tests for standardized error responses (errors.py)."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from starlette.testclient import TestClient
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from main.utils.errors import (
    ErrorResponse,
    RequestContextFilter,
    registerErrorHandlers,
)
from main.utils.request_id import RequestIDMiddleware, requestIdVar


class SampleBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=10)


@pytest.fixture
def app():
    application = FastAPI()
    application.add_middleware(RequestIDMiddleware)
    registerErrorHandlers(application)

    @application.get("/ok")
    def ok_route():
        return {"message": "success"}

    @application.get("/http-error")
    def http_error_route():
        raise HTTPException(status_code=404, detail="Resource not found")

    @application.get("/unhandled-error")
    def unhandled_error_route():
        raise RuntimeError("Something broke")

    @application.post("/validate")
    def validate_route(body: SampleBody):
        return {"name": body.name}

    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestErrorResponseModel:
    def test_error_response_structure(self):
        resp = ErrorResponse(error="test error", timestamp="2024-01-01T00:00:00Z", status_code=500)
        d = resp.model_dump()
        assert d["success"] is False
        assert d["error"] == "test error"
        assert d["detail"] is None
        assert d["request_id"] is None
        assert d["timestamp"] == "2024-01-01T00:00:00Z"
        assert d["status_code"] == 500

    def test_error_response_with_detail_and_request_id(self):
        resp = ErrorResponse(
            error="bad input",
            detail="field X is wrong",
            request_id="req-123",
            timestamp="2024-01-01T00:00:00Z",
            status_code=422,
        )
        d = resp.model_dump()
        assert d["detail"] == "field X is wrong"
        assert d["request_id"] == "req-123"
        assert d["status_code"] == 422


class TestRequestContextFilter:
    def test_injects_request_id_from_contextvar(self):
        f = RequestContextFilter()
        record = __import__("logging").LogRecord(
            name="test", level=10, pathname="", lineno=0, msg="test", args=(), exc_info=None
        )
        requestIdVar.set("req-abc")
        assert f.filter(record) is True
        assert record.request_id == "req-abc"

    def test_empty_request_id_default(self):
        f = RequestContextFilter()
        record = __import__("logging").LogRecord(
            name="test", level=10, pathname="", lineno=0, msg="test", args=(), exc_info=None
        )
        requestIdVar.set("")
        assert f.filter(record) is True
        assert record.request_id == ""


class TestHTTPExceptionHandler:
    def test_returns_structured_error(self, client):
        response = client.get("/http-error")
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
        assert body["error"] == "Resource not found"
        assert "request_id" in body
        assert "timestamp" in body

    def test_includes_request_id_header(self, client):
        response = client.get("/http-error")
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"] == response.json()["request_id"]


class TestValidationExceptionHandler:
    def test_returns_422_for_invalid_input(self, client):
        response = client.post("/validate", json={"name": ""})
        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "request_id" in body

    def test_returns_422_for_missing_body(self, client):
        response = client.post("/validate", json={})
        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert body["error"] == "Validation error"

    def test_valid_input_passes(self, client):
        response = client.post("/validate", json={"name": "hello"})
        assert response.status_code == 200
        assert response.json() == {"name": "hello"}


class TestGenericExceptionHandler:
    def test_returns_500_for_unhandled(self, client):
        response = client.get("/unhandled-error")
        assert response.status_code == 500
        body = response.json()
        assert body["success"] is False
        assert body["error"] == "Internal server error"
        assert "request_id" in body


class TestSuccessPassthrough:
    def test_ok_route_unaffected(self, client):
        response = client.get("/ok")
        assert response.status_code == 200
        assert response.json() == {"message": "success"}
