# Lean Mathlib 4 Documentation Search MCP Server

This project provides a Minimal MCP (Model Context Protocol) Server for searching Lean Mathlib 4 documentation. It allows LLMs to query Lean Mathlib 4 declarations and retrieve relevant documentation links and details. The MCP server is only available for VSCode at the moment.

## Features

- **Search Lean Mathlib 4 Documentation**: Query the documentation for declarations, modules, and instances.
- **MCP Server Integration**: Implements the MCP protocol for seamless integration with tools.
- **Local Data Handling**: Downloads and processes Lean Mathlib 4 documentation data locally after the first run.

## Prerequisites

- Python 3.11 or higher
- `requests` library
- `mcp` MCP Server library

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/CriticalLine/lean-mathlib-docs-mcp.git
   cd lean-mathlib-docs-mcp
   ```

2. Install the required Python dependencies:

   ```bash
   conda env create -f environment.yml
   conda activate lean-mathlib-docs-env
   ```

3. Ensure the `mcp.json` file is correctly configured in the `.vscode` folder or the project root.

## Usage

1. VSCode will automatically start the MCP server when you launch it with the appropriate configuration.
2. Query the server by explicitly using `#search_lean_doc <query>` or tell the LLM to use the search function.

## Project Structure

```plaintext
lean-mathlib-docs-mcp/
├── LICENSE
├── README.md
├── src/
│   ├── lean_docs_server.py
│   └── mcp.json
```

## Development

- test the mcp server
- add check the original code

## License

This project is licensed under the GPLv3 License. See the `LICENSE` file for details.
Prohibits all commercial use.

## Acknowledgments

- [Lean Mathlib 4](https://leanprover-community.github.io/mathlib4_docs/) for the documentation data.
- The MCP Server library for providing the protocol implementation.
