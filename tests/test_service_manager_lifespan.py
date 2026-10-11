"""Chained MCP lifespans on a shared service app.

Regression for the USER/STOCKSAPI port-3200 collision: both services share one
``getApp(port)`` instance, so direct ``lifespan_context =`` assignment lets the
last writer win and the loser's session manager never starts (live 500
``StreamableHTTPSessionManager task group was not initialized``).
"""

import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI

from main.utils.service_manager import adoptMcpLifespan


def _makeDummy(events: list[str], name: str) -> Any:
    @asynccontextmanager
    async def dummy(app: Any) -> Any:
        events.append(f"{name}-start")
        yield
        events.append(f"{name}-stop")

    return dummy


async def test_single_adoption_runs_lifespan() -> None:
    events: list[str] = []
    service = FastAPI()
    adoptMcpLifespan(service, SimpleNamespace(lifespan=_makeDummy(events, "only")))
    async with service.router.lifespan_context(service):
        assert events == ["only-start"]
    assert events == ["only-start", "only-stop"]


async def test_two_adoptions_run_both_in_order() -> None:
    events: list[str] = []
    service = FastAPI()
    adoptMcpLifespan(service, SimpleNamespace(lifespan=_makeDummy(events, "first")))
    adoptMcpLifespan(service, SimpleNamespace(lifespan=_makeDummy(events, "second")))
    async with service.router.lifespan_context(service):
        assert events == ["first-start", "second-start"]
    assert events == ["first-start", "second-start", "second-stop", "first-stop"]


async def test_none_previous_still_works() -> None:
    events: list[str] = []
    service = FastAPI()
    service.router.lifespan_context = None  # type: ignore[assignment]
    adoptMcpLifespan(service, SimpleNamespace(lifespan=_makeDummy(events, "only")))
    async with service.router.lifespan_context(service):
        assert events == ["only-start"]
    assert events == ["only-start", "only-stop"]
