"""MCP server integration tests (spec section 5)."""
import asyncio

from lean_mathlib_mcp import server


def test_all_tools_registered():
    tools = asyncio.run(server.server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "search_declaration", "get_entity", "search_by_signature",
        "search_by_notation", "search_by_domain_use", "search_by_conclusion",
        "search_hypothesis", "search_proof_complexity", "expand_dependencies",
        "find_usages", "recommend_related", "module_snapshot", "search_modules",
        "index_info", "batch_query",
    }
    assert names == expected


def test_dispatch_returns_valid_json_ready_payload():
    # Every tool returns a JSON-serializable dict (the server wraps it in a string).
    import json

    payload = server._dispatch("index_info", {})
    json.dumps(payload)  # must not raise
    assert "summary" in payload


def test_read_only_contract():
    # The server exposes no mutation tools; confirm the surface is query-only.
    tools = asyncio.run(server.server.list_tools())
    assert all(
        not n.startswith(("write", "delete", "update", "exec", "run", "mutate"))
        for n in (t.name for t in tools)
    )
