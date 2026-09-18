"""Pytest configuration: offline sample mode + make the package importable."""
import os
import sys
from pathlib import Path

# Use the committed offline sample fixture (no network, deterministic).
os.environ["LEAN_MATHLIB_DATA_SOURCE"] = "sample"
os.environ.setdefault("LEAN_MATHLIB_SAMPLE", "true")

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import lean_mathlib_mcp.server as server  # noqa: E402


def pytest_sessionstart(session):
    # Warm the index once for the whole session.
    server.get_index()
