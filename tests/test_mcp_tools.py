"""wireRouteTools: route metadata -> MCP tool, without hand-written wrappers.

`from __future__ import annotations` is deliberate: it makes every annotation in
the fixture routes below a string, the worst case for the helper's annotation
transfer. The helper's own module must NOT use it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastmcp import Client, FastMCP

from main.utils.mcp_tools import wireRouteTools


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

    def getWalletUser():
        return {"userId": 1}

    @router.get("/plain")
    def plain_route():
        return {"plain": True}

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

    @router.post("/boom", operation_id="boom")
    def boom_route(
        currentUser: dict = Depends(getWalletUser),
        db=Depends(lambda: None),
    ) -> dict:
        """Fails."""
        return {}

    names = wireRouteTools(
        mcp,
        router,
        resolveIdentity=routeIdentity or (lambda authorization, db: {"userId": 7}),
        sessionFactory=sessionFactory or (lambda: None),
    )
    return mcp, names, calls


async def test_only_operation_id_routes_become_tools():
    mcp, names, _ = build()
    toolNames = {tool.name for tool in await listTools(mcp)}
    assert toolNames == {"wallet_positions", "record_entry", "boom"}
    assert "plain_route" not in toolNames
    assert set(names) == toolNames


async def test_depends_params_hidden_and_authorization_added():
    mcp, _, _ = build()
    tool = next(t for t in await listTools(mcp) if t.name == "record_entry")
    properties = tool.input_schema["properties"]
    assert set(properties) == {"side", "quantity", "costs", "authorization"}
    assert "currentUser" not in properties and "db" not in properties
    assert tool.input_schema["required"] == ["side", "quantity"]
    assert properties["authorization"]["default"] == ""


async def test_query_alias_stripped():
    mcp, _, _ = build()
    tool = next(t for t in await listTools(mcp) if t.name == "wallet_positions")
    properties = tool.input_schema["properties"]
    assert "fromIso" in properties
    assert "from" not in properties


async def test_constraints_preserved():
    mcp, _, _ = build()
    tools = {t.name: t for t in await listTools(mcp)}
    assert tools["wallet_positions"].input_schema["properties"]["limit"]["minimum"] == 1
    assert tools["wallet_positions"].input_schema["properties"]["limit"]["maximum"] == 100
    assert tools["record_entry"].input_schema["properties"]["quantity"]["exclusiveMinimum"] == 0
    assert tools["record_entry"].input_schema["properties"]["costs"]["minimum"] == 0


async def test_annotations_resolve_without_future_import():
    """Every annotation above is a string; the helper must resolve them anyway."""
    mcp, _, _ = build()
    tools = {t.name: t for t in await listTools(mcp)}
    assert tools["record_entry"].input_schema["properties"]["side"]["enum"] == ["Compra", "Venda"]


async def test_docstring_propagated():
    mcp, _, _ = build()
    tool = next(t for t in await listTools(mcp) if t.name == "wallet_positions")
    assert "Positions for the wallet." in tool.description
    assert "PARAMETERS:" in tool.description


async def test_tool_body_delegates_with_identity_and_session():
    spy = Spy()
    seen = {}

    def resolver(authorization, db):
        seen["arg"] = authorization
        return {"userId": 9}

    mcp, _, calls = build(routeIdentity=resolver, sessionFactory=spy.session)
    async with Client(mcp) as client:
        await client.call_tool("wallet_positions", {"ticker": "PETR4", "authorization": "Bearer abc"})
    assert seen["arg"] == "Bearer abc"
    assert calls[-1]["currentUser"] == {"userId": 9}
    assert calls[-1]["ticker"] == "PETR4"
    assert spy.closed == 1


async def test_missing_required_arg_is_rejected():
    mcp, _, _ = build()
    async with Client(mcp) as client:
        result = await client.call_tool("record_entry", {"quantity": 1.0}, raise_on_error=False)
    assert result.is_error


async def test_session_closed_when_identity_raises():
    spy = Spy()

    def reject(authorization, db):
        raise HTTPException(status_code=401, detail="Session revoked")

    mcp, _, _ = build(routeIdentity=reject, sessionFactory=spy.session)
    async with Client(mcp) as client:
        result = await client.call_tool("boom", {}, raise_on_error=False)
    assert result.is_error
    assert spy.closed == 1
