"""Standardized input validation models for all endpoints."""

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """POST /auth/register"""

    name: str = Field(..., min_length=1, max_length=100, description="User name")
    email: str = Field(..., min_length=5, max_length=255, description="User email")
    password: str = Field(..., min_length=6, max_length=128, description="User password")


class LoginRequest(BaseModel):
    """POST /auth/login"""

    email: str = Field(..., min_length=5, max_length=255, description="User email")
    password: str = Field(..., min_length=6, max_length=128, description="User password")


class UpgradeDeveloperRequest(BaseModel):
    """POST /user/upgradeDeveloperStarter or /user/upgradeDeveloperEnterprise"""

    name: str = Field(..., min_length=1, max_length=100, description="Developer name")


class CreateSessionRequest(BaseModel):
    """POST /prometheus/sessions"""

    title: str = Field(..., min_length=1, max_length=200, description="Session title")


class UpdateTitleRequest(BaseModel):
    """PUT /prometheus/sessions/{sessionId}/title"""

    title: str = Field(..., min_length=1, max_length=200, description="Session title")


class ChatRequest(BaseModel):
    """POST /prometheus/sessions/{sessionId}/chat"""

    text: str = Field(..., min_length=1, max_length=10000, description="Chat message")
