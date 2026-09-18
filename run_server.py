#!/usr/bin/env python
"""Launcher for the Lean Mathlib 4 Docs Search MCP Server.

This thin entrypoint guarantees the packaged source tree is importable even when
the project is run directly (without `pip install -e .`), e.g. from an MCP client
config that invokes `python run_server.py`.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from lean_mathlib_mcp.server import main

if __name__ == "__main__":
    main()
