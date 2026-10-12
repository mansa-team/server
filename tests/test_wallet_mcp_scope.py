"""Wallet FastMCP (/wallet/mcp) scoping tests — Task 2 of the FastMCP replacement plan."""

import pytest

EXPECTED_MCP_TOOLS = {
    "wallet_positions",
    "wallet_rebalance",
    "wallet_summary",
    "wallet_allocation",
    "wallet_earnings",
    "wallet_performance",
    "wallet_progression_series",
    "record_entry",
    "set_rating",
    "explain_twr",
    "wallet_progression",
}


async def test_mcp_exposes_exact_11():
    from main.controller.wallet_controller import walletMcp

    tools = await walletMcp.list_tools()
    assert {tool.name for tool in tools} == EXPECTED_MCP_TOOLS


async def test_all_tools_have_anthropic_docstrings():
    from main.controller.wallet_controller import walletMcp

    tools = await walletMcp.list_tools()
    for tool in tools:
        for section in ("PARAMETERS:", "RESPONSE format:", "WORKFLOW:", "EXAMPLES:"):
            assert section in (tool.description or ""), f"{tool.name} missing {section}"


async def test_wallet_progression_schema_bounds():
    from main.controller.wallet_controller import walletMcp

    tools = await walletMcp.list_tools()
    props = next(tool for tool in tools if tool.name == "wallet_progression").parameters["properties"]
    assert props["max_points"]["minimum"] == 2
    assert props["max_points"]["maximum"] == 2000
