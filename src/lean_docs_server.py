"""
Minimal MCP Server for Lean Mathlib 4 Documentation Search
"""

import asyncio, os, re, requests
from typing import Any, Dict, List
import json

# mcp server imports
from mcp.server import Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
from mcp.types import Tool, TextContent
from mcp.server.lowlevel.server import NotificationOptions

# Helper functions for searching Lean documentation
# download the data
def download_lean_doc_data():
    url = "https://leanprover-community.github.io/mathlib4_docs//declarations/declaration-data.bmp"
    try:
        response = requests.get(url)
        # save to local file in the same folder of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(current_dir, "declaration-data.bmp"), "wb") as f:
            f.write(response.content)
    except requests.RequestException as e:
        print(f"Failed to download data: {e}")

def search_declarations(
    query: str, data: Dict, max_results: int = 5
) -> List[Dict[str, Any]]:
    """Search declarations"""
    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for decl_name, decl_data in data["declarations"].items():
        if pattern.search(decl_name):
            result = {
                "name": decl_name,
                "kind": decl_data.get("kind", "unknown"),
                "docLink": decl_data.get("docLink", ""),
                "type": "declaration",
            }
            results.append(result)
            if len(results) >= max_results:
                break

    return results

def get_the_source_code_url(doc_link: str) -> str:
    """Convert documentation link to source code URL"""
    base_url = "https://leanprover-community.github.io/mathlib4_docs/"
    if doc_link.startswith("./"):
        doc_link = doc_link[2:]
    source_url = f"{base_url}{doc_link}"
    return source_url

def format_result(result: Dict[str, Any]) -> str:
    """Format a single result as a readable string"""
    if result["type"] == "declaration":
        return f"""Declaration: {result['name']}
Kind: {result['kind']}
Documentation Link: {result['docLink']}
{'-'*5}"""

    elif result["type"] == "instance":
        return f"""Instance: {result['name']}
{'-'*5}"""

    elif result["type"] == "module":
        imported_by = result["importedBy"][:5]
        imported_str = "\n  ".join(imported_by)
        return f"""Module: {result['name']}
URL: {result['url']}
Imported by: {imported_str}{'...' if len(result['importedBy']) > 5 else ''}
{'-'*5}"""

    return ""

def fetch_lean_documentation(queries: List[str], max_results: int = 10, search_type: str = "all") -> List[Dict[str, Any]]:
    """Search Lean documentation and return the content"""
    results = []
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)  # Change working directory to the script's directory
    # check if declaration-data.bmp exists, if not, download it
    if not os.path.exists("declaration-data.bmp"):
        download_lean_doc_data()
    # Load data from local JSON file
    with open("declaration-data.bmp", "r", encoding="utf-8") as f:
        data = json.load(f)

    for query in queries:
        print(f"\n{'='*80}")
        print(f"Search: {query}")
        print(f"{'='*80}")

        if search_type in ("all", "declarations"):
            decl_results = search_declarations(query, data, max_results)
            for result in decl_results:
                formatted = format_result(result)
                print(formatted)
                results.append({"text": formatted})

    return results

def test_fetch_lean_documentation():
    queries = ["add", "mul"]
    results = fetch_lean_documentation(queries, max_results=3, search_type="all")
    for res in results:
        print(res["text"])

# Create the MCP server instance
server = Server("random-number-server")

@server.list_tools()
async def list_tools() -> List[Tool]:
    """return toolchains"""
    return [Tool(
            name="search_lean_doc",
            description="Search Lean Mathlib 4 documentation",
            inputSchema={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Search queries"
                    }
                },
                "required": ["queries"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Call the specified tool with arguments and return the result."""
    if name == "search_lean_doc":
        queries = arguments.get("queries", [])
        return [TextContent(type="text", text=result["text"]) for result in fetch_lean_documentation(queries)]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main() -> None:
    """Main function"""
    # Set default notification_options
    notification_options = NotificationOptions(tools_changed=False)

    # Start the MCP server with stdio transport
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="Lean Mathlib 4 Doc Search MCP Server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=notification_options,
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())