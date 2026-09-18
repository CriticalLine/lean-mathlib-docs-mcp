"""Real MCP stdio end-to-end test.

Launches the server as a subprocess and speaks the MCP protocol over stdio,
exercising the two primary query tools (search_declaration, get_entity) to
confirm they return non-empty results after the mathlib_only default fix.
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENV = dict(os.environ, LEAN_MATHLIB_DATA_SOURCE="sample", PYTHONPATH=os.path.join(ROOT, "src"))


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(ROOT, "run_server.py")],
        env=ENV,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("server:", init.server_info.name, init.server_info.version)

            tools = await session.list_tools()
            print("tool_count:", len(tools.tools))

            # 1) search_declaration "Add" — should be non-empty now.
            res = await session.call_tool("search_declaration", {"query": "Add", "max_results": 5})
            text = res.content[0].text
            payload = json.loads(text)
            hits = payload["hits"]
            print("search_declaration(Add) -> hits:", len(hits))
            assert len(hits) > 0, "search_declaration returned 0 hits (mathlib_only bug?)"
            print("  sample:", hits[0]["entity"]["full_name"], "type=", hits[0]["entity"]["entity_type"])

            # 2) get_entity a known enriched declaration.
            res = await session.call_tool("get_entity", {"full_name": "Nat.add"})
            ent = json.loads(res.content[0].text)
            print("get_entity(Nat.add) -> id:", ent["id"], "signature?", bool(ent.get("type_signature")))
            assert ent["id"] == "decl:Nat.add"

            # 3) search_by_domain_use sanity.
            res = await session.call_tool(
                "search_by_domain_use", {"domain": "Algebra", "max_results": 3}
            )
            d = json.loads(res.content[0].text)
            print("search_by_domain_use(Algebra) -> hits:", len(d["hits"]))
            assert len(d["hits"]) > 0

            print("E2E_OK")
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
