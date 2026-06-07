"""Tests for input validation models (schemas/inputs.py)."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pydantic import ValidationError
from main.schemas.inputs import (
    RegisterRequest,
    LoginRequest,
    UpgradeDeveloperRequest,
    CreateSessionRequest,
    UpdateTitleRequest,
    ChatRequest,
)


class TestRegisterRequest:
    def test_valid(self):
        r = RegisterRequest(name="Alice", email="alice@example.com", password="secret123")
        assert r.name == "Alice"
        assert r.email == "alice@example.com"

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            RegisterRequest(name="", email="alice@example.com", password="secret123")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            RegisterRequest(name="A" * 101, email="alice@example.com", password="secret123")

    def test_email_too_short(self):
        with pytest.raises(ValidationError):
            RegisterRequest(name="Alice", email="a@b", password="secret123")

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            RegisterRequest(name="Alice", email="alice@example.com", password="ab")


class TestLoginRequest:
    def test_valid(self):
        r = LoginRequest(email="alice@example.com", password="secret123")
        assert r.email == "alice@example.com"

    def test_email_too_short(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b", password="secret123")

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="alice@example.com", password="ab")


class TestUpgradeDeveloperRequest:
    def test_valid(self):
        r = UpgradeDeveloperRequest(name="MyApp")
        assert r.name == "MyApp"

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            UpgradeDeveloperRequest(name="")


class TestCreateSessionRequest:
    def test_valid(self):
        r = CreateSessionRequest(title="New Chat")
        assert r.title == "New Chat"

    def test_empty_title(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(title="")

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(title="T" * 201)


class TestUpdateTitleRequest:
    def test_valid(self):
        r = UpdateTitleRequest(title="Updated Title")
        assert r.title == "Updated Title"

    def test_empty_title(self):
        with pytest.raises(ValidationError):
            UpdateTitleRequest(title="")


class TestChatRequest:
    def test_valid(self):
        r = ChatRequest(text="Hello AI")
        assert r.text == "Hello AI"

    def test_empty_text(self):
        with pytest.raises(ValidationError):
            ChatRequest(text="")

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            ChatRequest(text="X" * 10001)

    def test_max_length_boundary(self):
        r = ChatRequest(text="X" * 10000)
        assert len(r.text) == 10000
