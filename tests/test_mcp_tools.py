"""mcpToolDecorator: route metadata -> MCP tool, without hand-written wrappers.

`from __future__ import annotations` is deliberate: it makes every annotation in
the fixture routes below a string, the worst case for the helper's annotation
transfer. The helper's own module must NOT use it.

`mcpToolDecorator` returns a decorator that must sit ABOVE `@router.<verb>(...)`, so
`build()` binds it before declaring the routes and stacks it on each one.
"""

from __future__ import annotations

from typing import Literal

import pytest
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastmcp import Client, FastMCP

from main.utils.mcp import buildToolFromRoute, mcpToolDecorator


async def listTools(mcp):
    async with Client(mcp) as client:
        return await client.list_tools()


class Spy:
    def __init__(self):
        self.closed = 0

    def session(self):
        spy = self

        class Session:
            def close(self):
                spy.closed += 1

        return Session()


def build(routeIdentity=None, sessionFactory=None):
    """One router: three MCP routes (operation_id) and one plain HTTP route."""
    mcp = FastMCP("test-mcp")
    router = APIRouter(prefix="/wallet")
    calls = []
    tool = mcpToolDecorator(
        mcp,
        router,
        resolveIdentity=routeIdentity or (lambda authorization, db: {"userId": 7}),
        sessionFactory=sessionFactory or (lambda: None),
    )

    def getWalletUser():
        return {"userId": 1}

    @router.get("/plain")
    def plain_route():
        return {"plain": True}

    @tool
    @router.get("/positions", operation_id="wallet_positions")
    def positions_route(
        ticker: str | None = None,
        fromIso: str | None = Query(default=None, alias="from"),
        limit: int = Query(default=20, ge=1, le=100),
        currentUser: dict = Depends(getWalletUser),
        db=Depends(lambda: None),
    ) -> dict:
        """Positions for the wallet.

        PARAMETERS:
        - `ticker` (optional): one ticker.
        """
        calls.append({"currentUser": currentUser, "db": db, "ticker": ticker, "fromIso": fromIso})
        return {"ticker": ticker, "from": fromIso}

    @tool
    @router.post("/record", operation_id="record_entry")
    def record_route(
        side: Literal["Compra", "Venda"],
        quantity: float = Body(..., gt=0),
        costs: float = Body(default=0.0, ge=0),
        currentUser: dict = Depends(getWalletUser),
        db=Depends(lambda: None),
    ) -> dict:
        """Record a trade."""
        return {"side": side, "quantity": quantity}

    @tool
    @router.post("/boom", operation_id="boom")
    def boom_route(
        currentUser: dict = Depends(getWalletUser),
        db=Depends(lambda: None),
    ) -> dict:
        """Fails."""
        return {}

    return mcp, calls


async def test_only_operation_id_routes_become_tools():
    mcp, _ = build()
    toolNames = {tool.name for tool in await listTools(mcp)}
    assert toolNames == {"wallet_positions", "record_entry", "boom"}
    assert "plain_route" not in toolNames


async def test_tool_name_is_operation_id():
    mcp, _ = build()
    tools = {t.name: t for t in await listTools(mcp)}
    assert tools["wallet_positions"].description.startswith("Positions for the wallet.")


async def test_depends_params_hidden_and_authorization_added():
    mcp, _ = build()
    tool = next(t for t in await listTools(mcp) if t.name == "record_entry")
    properties = tool.input_schema["properties"]
    assert set(properties) == {"side", "quantity", "costs", "authorization"}
    assert "currentUser" not in properties and "db" not in properties
    assert tool.input_schema["required"] == ["side", "quantity"]
    assert properties["authorization"]["default"] == ""


async def test_query_alias_stripped():
    mcp, _ = build()
    tool = next(t for t in await listTools(mcp) if t.name == "wallet_positions")
    properties = tool.input_schema["properties"]
    assert "fromIso" in properties
    assert "from" not in properties


async def test_constraints_preserved():
    mcp, _ = build()
    tools = {t.name: t for t in await listTools(mcp)}
    assert tools["wallet_positions"].input_schema["properties"]["limit"]["minimum"] == 1
    assert tools["wallet_positions"].input_schema["properties"]["limit"]["maximum"] == 100
    assert tools["record_entry"].input_schema["properties"]["quantity"]["exclusiveMinimum"] == 0
    assert tools["record_entry"].input_schema["properties"]["costs"]["minimum"] == 0


async def test_annotations_resolve_without_future_import():
    """Every annotation above is a string; the helper must resolve them anyway."""
    mcp, _ = build()
    tools = {t.name: t for t in await listTools(mcp)}
    assert tools["record_entry"].input_schema["properties"]["side"]["enum"] == ["Compra", "Venda"]


def unresolvedAnnotationRoute(unresolvableType: UnresolvableType = None) -> dict:  # noqa: F821  # deliberately undefined
    """Annotation with no binding in this module's globals: eval_str cannot resolve it."""
    return {}


def test_unresolvable_annotation_falls_back_to_raw_string():
    """The helper degrades to raw annotations instead of raising when eval_str fails."""
    router = APIRouter(prefix="/wallet")
    router.get("/unresolvable", operation_id="unresolved_annotation")(unresolvedAnnotationRoute)

    tool = buildToolFromRoute(router.routes[-1], lambda authorization, db: {"userId": 7}, lambda: None)

    assert tool.__name__ == "unresolved_annotation"
    assert tool.__annotations__["unresolvableType"] == "UnresolvableType"
    assert tool.__signature__.parameters["unresolvableType"].annotation == "UnresolvableType"


async def test_docstring_propagated():
    mcp, _ = build()
    tool = next(t for t in await listTools(mcp) if t.name == "wallet_positions")
    assert "Positions for the wallet." in tool.description
    assert "PARAMETERS:" in tool.description


async def test_response_param_hidden_and_fresh_per_call():
    """A route writing headers on `Response` gets a fresh one injected, never exposed as an argument."""
    mcp = FastMCP("test-mcp")
    router = APIRouter(prefix="/stocks")
    tool = mcpToolDecorator(mcp, router)
    responses = []

    @tool
    @router.get("/fields", operation_id="list_fields")
    def list_fields(response: Response) -> dict:
        """Fields."""
        response.headers["Cache-Control"] = "public, max-age=1"
        responses.append(response)
        return {}

    async with Client(mcp) as client:
        assert (await listTools(mcp))[0].input_schema["properties"] == {}
        await client.call_tool("list_fields", {})
        await client.call_tool("list_fields", {})
    assert len(responses) == 2
    assert responses[0] is not responses[1]
    assert responses[0].headers["Cache-Control"] == "public, max-age=1"
    assert "authorization" not in (await listTools(mcp))[0].input_schema["properties"]


async def test_tool_body_delegates_with_identity_and_session():
    spy = Spy()
    seen = []

    def resolver(authorization, db):
        seen.append(authorization)
        return {"userId": 9}

    mcp, calls = build(routeIdentity=resolver, sessionFactory=spy.session)
    async with Client(mcp) as client:
        await client.call_tool("wallet_positions", {"ticker": "PETR4", "authorization": "Bearer abc"})
        await client.call_tool("wallet_positions", {"ticker": "VALE3"})
    assert seen == ["Bearer abc", ""]
    assert calls[-1]["currentUser"] == {"userId": 9}
    assert calls[-1]["ticker"] == "VALE3"
    assert spy.closed == 2  # one fresh session per call, both closed


async def test_missing_required_arg_is_rejected():
    mcp, _ = build()
    async with Client(mcp) as client:
        result = await client.call_tool("record_entry", {"quantity": 1.0}, raise_on_error=False)
    assert result.is_error


async def test_session_closed_when_identity_raises():
    spy = Spy()

    def reject(authorization, db):
        raise HTTPException(status_code=401, detail="Session revoked")

    mcp, _ = build(routeIdentity=reject, sessionFactory=spy.session)
    async with Client(mcp) as client:
        result = await client.call_tool("boom", {}, raise_on_error=False)
    assert result.is_error
    assert spy.closed == 1


def test_guard_raises_without_an_underlying_route():
    """Decorator stacked on a function that is not a route."""
    mcp = FastMCP("test-mcp")
    router = APIRouter()
    tool = mcpToolDecorator(mcp, router, resolveIdentity=lambda authorization, db: {}, sessionFactory=lambda: None)

    with pytest.raises(RuntimeError, match="not_a_route"):

        @tool
        def not_a_route():
            return {}


def test_guard_raises_without_operation_id():
    """Route exists but declares no operation_id (so it names no tool)."""
    mcp = FastMCP("test-mcp")
    router = APIRouter()
    tool = mcpToolDecorator(mcp, router, resolveIdentity=lambda authorization, db: {}, sessionFactory=lambda: None)

    with pytest.raises(RuntimeError, match="no_id_route"):

        @tool
        @router.get("/no-id")
        def no_id_route():
            return {}


def test_missing_session_factory_raises_for_db_route():
    """A route declaring `db` with no sessionFactory is a registration error, not a silent no-op."""
    mcp = FastMCP("test-mcp")
    router = APIRouter()
    tool = mcpToolDecorator(mcp, router)

    with pytest.raises(RuntimeError, match="sessionFactory"):

        @tool
        @router.get("/needs-db", operation_id="needs_db")
        def needs_db(db=Depends(lambda: None)):
            return {}


def test_missing_resolve_identity_raises_for_identity_route():
    """A route declaring `currentUser` with no resolveIdentity is a registration error."""
    mcp = FastMCP("test-mcp")
    router = APIRouter()
    tool = mcpToolDecorator(mcp, router, sessionFactory=lambda: None)

    with pytest.raises(RuntimeError, match="resolveIdentity"):

        @tool
        @router.get("/needs-identity", operation_id="needs_identity")
        def needs_identity(currentUser=Depends(lambda: None)):
            return {}
